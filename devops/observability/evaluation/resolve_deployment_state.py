#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
K8S_ROOT = ROOT / "devops" / "k8s"
STATE_ROOT = ROOT / "devops" / "state"


def parse_args():
    parser = argparse.ArgumentParser(description="Resolve or persist deployment image state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--app", required=True)
    resolve_parser.add_argument("--output")

    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--app", required=True)
    promote_parser.add_argument("--change-id", default="")
    promote_parser.add_argument("--git-sha", default="")
    promote_parser.add_argument("--workflow-run-id", default="")
    promote_parser.add_argument("--source", default="observability")
    promote_parser.add_argument("--output")

    return parser.parse_args()


def image_tag_path(app_name: str) -> Path:
    return K8S_ROOT / app_name / "image-tag.yaml"


def state_path(app_name: str) -> Path:
    return STATE_ROOT / f"{app_name}.json"


def parse_image_tag_text(text: str) -> dict:
    repository = None
    tag = None
    for line in text.splitlines():
        repo_match = re.match(r"^\s*repository:\s*(\S+)\s*$", line)
        if repo_match:
            repository = repo_match.group(1)
        tag_match = re.match(r"^\s*tag:\s*(\S+)\s*$", line)
        if tag_match:
            tag = tag_match.group(1)
    if not repository or not tag:
        raise ValueError("Could not parse repository/tag from image-tag.yaml")
    return {
        "repository": repository,
        "tag": tag,
        "version": f"{repository}:{tag}",
    }


def read_current_image(app_name: str) -> dict:
    path = image_tag_path(app_name)
    if not path.exists():
        raise FileNotFoundError(f"Image tag manifest not found: {path}")
    return parse_image_tag_text(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def read_previous_image(app_name: str) -> dict | None:
    relative_path = image_tag_path(app_name).relative_to(ROOT).as_posix()
    history = git("log", "--format=%H", "--", relative_path).splitlines()
    if len(history) < 2:
        return None
    prior_commit = history[1]
    prior_text = git("show", f"{prior_commit}:{relative_path}")
    image = parse_image_tag_text(prior_text)
    image["git_commit"] = prior_commit
    return image


def read_state(app_name: str) -> dict | None:
    path = state_path(app_name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_state(app_name: str) -> dict:
    current = read_current_image(app_name)
    previous = read_previous_image(app_name)
    existing_state = read_state(app_name)
    healthy = None
    healthy_source = "state_file"

    if existing_state:
        healthy = existing_state.get("last_known_healthy")

    if not healthy and previous:
        healthy = {
            "repository": previous["repository"],
            "tag": previous["tag"],
            "version": previous["version"],
            "source_commit": previous["git_commit"],
        }
        healthy_source = "previous_version_fallback"

    return {
        "app_name": app_name,
        "manifest_dir": f"devops/k8s/{app_name}",
        "image_tag_path": f"devops/k8s/{app_name}/image-tag.yaml",
        "state_path": f"devops/state/{app_name}.json",
        "current": current,
        "previous": previous,
        "last_known_healthy": healthy,
        "last_known_healthy_source": healthy_source if healthy else "missing",
    }


def write_json(path_str: str | None, payload: dict) -> None:
    text = json.dumps(payload, indent=2) + "\n"
    if path_str:
      path = Path(path_str)
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(text, encoding="utf-8")
    else:
      print(text, end="")


def promote_state(app_name: str, change_id: str, git_sha: str, workflow_run_id: str, source: str) -> dict:
    current = read_current_image(app_name)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "app_name": app_name,
        "manifest_dir": f"devops/k8s/{app_name}",
        "image_tag_path": f"devops/k8s/{app_name}/image-tag.yaml",
        "last_updated_at": now,
        "current_candidate": {
            **current,
            "change_id": change_id,
            "git_sha": git_sha,
            "workflow_run_id": workflow_run_id,
            "source": source,
            "updated_at": now,
        },
        "last_known_healthy": {
            **current,
            "change_id": change_id,
            "git_sha": git_sha,
            "workflow_run_id": workflow_run_id,
            "source": source,
            "updated_at": now,
        },
    }
    path = state_path(app_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main():
    args = parse_args()
    if args.command == "resolve":
        payload = resolve_state(args.app)
        write_json(args.output, payload)
        return

    payload = promote_state(
        app_name=args.app,
        change_id=args.change_id,
        git_sha=args.git_sha,
        workflow_run_id=args.workflow_run_id,
        source=args.source,
    )
    write_json(args.output, payload)


if __name__ == "__main__":
    main()
