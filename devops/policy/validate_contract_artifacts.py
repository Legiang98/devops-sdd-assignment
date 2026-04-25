#!/usr/bin/env python3
"""Validate deterministic contract artifacts produced from a spec."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from devops.spec.specs import load_resolved_spec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated contract artifacts")
    parser.add_argument("--spec", required=True, help="Path to spec YAML")
    parser.add_argument("--release-dir", required=True, help="Path to release directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    release_dir = Path(args.release_dir)

    spec = load_resolved_spec(spec_path)
    rules = json.loads((release_dir / "rules.json").read_text(encoding="utf-8"))
    deploy_manifest = json.loads(
        (release_dir / "deploy_manifest.json").read_text(encoding="utf-8")
    )

    violations: list[str] = []

    expected_change_id = spec["change_id"]
    if rules.get("release_id") != expected_change_id:
        violations.append("rules.release_id must match spec.change_id")

    if deploy_manifest.get("release_id") != expected_change_id:
        violations.append("deploy_manifest.release_id must match spec.change_id")

    expected_stages = spec["workflow_change"]["baseline_stages"][:]
    if spec["workflow_change"].get("new_stage"):
        expected_stages.append(spec["workflow_change"]["new_stage"])

    actual_stages = rules["workflow"]["stages"]
    if len(expected_stages) != len(actual_stages):
        violations.append("workflow stage count mismatch")

    for index, expected in enumerate(expected_stages):
        if index >= len(actual_stages):
            violations.append(f"missing stage at index {index}: {expected['name']}")
            continue

        actual = actual_stages[index]
        if actual.get("name") != expected.get("name"):
            violations.append(f"stage[{index}] name mismatch")

        expected_threshold = expected["required_when"]["amount_gte"]
        actual_threshold = actual["required_when"]["amount_gte"]
        if actual_threshold != expected_threshold:
            violations.append(
                f"stage[{index}] threshold mismatch: expected {expected_threshold}, got {actual_threshold}"
            )

    report = {
        "release_id": expected_change_id,
        "spec": str(spec_path),
        "release_dir": str(release_dir),
        "status": "pass" if not violations else "fail",
        "violations": violations,
    }

    evidence_dir = release_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "contract-policy-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    if violations:
        print("Contract artifact validation failed:")
        for violation in violations:
            print(f"- {violation}")
        raise SystemExit(1)

    print("Contract artifact validation passed")


if __name__ == "__main__":
    main()
