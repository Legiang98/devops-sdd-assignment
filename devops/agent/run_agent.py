#!/usr/bin/env python
import argparse
import json
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate release artifacts from a change spec")
    parser.add_argument("--spec", required=True, help="Path to YAML spec")
    parser.add_argument("--output-root", default="build/releases", help="Release root")
    parser.add_argument(
        "--simulate-mismatch",
        action="store_true",
        help="Intentionally generate wrong threshold for policy-gate demo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    release_id = spec["change_id"]
    output_dir = Path(args.output_root) / release_id
    evidence_dir = output_dir / "evidence"
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    baseline = spec["workflow_change"]["baseline_stages"][0]
    new_stage = spec["workflow_change"].get("new_stage")

    stages = [baseline]
    if new_stage:
        stage_copy = json.loads(json.dumps(new_stage))
        if args.simulate_mismatch and stage_copy["name"] == "finance":
            stage_copy["required_when"]["amount_gte"] = 1250
        stages.append(stage_copy)

    rules = {
        "release_id": release_id,
        "service": spec["service"],
        "workflow": {"stages": stages},
    }

    (output_dir / "rules.json").write_text(
        json.dumps(rules, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "release_id.txt").write_text(f"{release_id}\n", encoding="utf-8")

    deploy_manifest = {
        "release_id": release_id,
        "deployment": spec["deployment"],
        "runtime": {
            "rules_path": "rules.json",
            "release_id_file": "release_id.txt",
        },
    }
    (output_dir / "deploy_manifest.json").write_text(
        json.dumps(deploy_manifest, indent=2) + "\n", encoding="utf-8"
    )

    agent_evidence = {
        "spec": str(spec_path),
        "release_id": release_id,
        "simulate_mismatch": args.simulate_mismatch,
        "generated_files": [
            "rules.json",
            "release_id.txt",
            "deploy_manifest.json",
        ],
    }
    (evidence_dir / "agent-output.json").write_text(
        json.dumps(agent_evidence, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Generated release artifacts: {output_dir}")


if __name__ == "__main__":
    main()
