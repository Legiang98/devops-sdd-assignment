#!/usr/bin/env python3
"""Resolve the single spec that should drive a feat/* branch workflow."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan changed specs for feat/* workflow")
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to diff against when --spec is not provided",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Git ref to diff up to when --spec is not provided",
    )
    parser.add_argument(
        "--spec",
        help="Explicit spec path. Skips git diff scanning when provided.",
    )
    parser.add_argument(
        "--github-output",
        help="Optional path to GitHub Actions output file.",
    )
    return parser.parse_args()


def changed_spec_paths(base_ref: str, head_ref: str) -> list[Path]:
    cmd = ["git", "diff", "--name-only", base_ref, head_ref]
    output = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    results: list[Path] = []
    for line in output.splitlines():
        value = line.strip()
        if not value:
            continue
        if fnmatch.fnmatch(value, "applications/*/specs/*.yaml"):
            results.append(Path(value))
    return results


def load_release_id(spec_path: Path) -> str:
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise SystemExit(f"Expected mapping YAML in spec: {spec_path}")
    release_id = raw.get("change_id")
    if not release_id:
        raise SystemExit(f"Spec is missing change_id: {spec_path}")
    return str(release_id)


def resolve_spec(args: argparse.Namespace) -> dict[str, str]:
    if args.spec:
        spec_path = Path(args.spec)
    else:
        specs = changed_spec_paths(args.base_ref, args.head_ref)
        if not specs:
            raise SystemExit("No changed spec file detected for feat/* workflow")
        if len(specs) != 1:
            joined = "\n".join(str(path) for path in specs)
            raise SystemExit(
                "Expected exactly one changed spec file for feat/* workflow:\n"
                f"{joined}"
            )
        spec_path = specs[0]

    if not spec_path.exists():
        raise SystemExit(f"Spec file not found: {spec_path}")

    app_path = spec_path.parents[1]
    return {
        "spec_file": str(spec_path),
        "release_id": load_release_id(spec_path),
        "app_path": str(app_path),
        "manifest_path": f"devops/k8s/{app_path.name}",
    }


def main() -> None:
    args = parse_args()
    payload = resolve_spec(args)

    if args.github_output:
        output_path = Path(args.github_output)
        with output_path.open("a", encoding="utf-8") as handle:
            for key, value in payload.items():
                handle.write(f"{key}={value}\n")
        return

    print(json.dumps(payload))


if __name__ == "__main__":
    main()
