#!/usr/bin/env python
import argparse
import ast
import json
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Policy gate: generated code alignment")
    parser.add_argument("--spec", required=True, help="Path to spec YAML")
    parser.add_argument("--release-dir", required=True, help="Path to release directory")
    return parser.parse_args()


def extract_constants(module_path: Path) -> dict[str, object]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    constants: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(node.value, ast.Constant):
            constants[target.id] = node.value.value
        elif isinstance(node.value, ast.List):
            values: list[object] = []
            for item in node.value.elts:
                if isinstance(item, ast.Constant):
                    values.append(item.value)
            constants[target.id] = values
    return constants


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    release_dir = Path(args.release_dir)

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    codegen_report_path = release_dir / "evidence" / "codegen-report.json"
    codegen_report = json.loads(codegen_report_path.read_text(encoding="utf-8"))

    module_path = Path(codegen_report["module_path"])
    module_constants = extract_constants(module_path)

    violations: list[str] = []

    expected_baseline = [
        stage["name"] for stage in spec["workflow_change"]["baseline_stages"]
    ]
    expected_new_stage = spec["workflow_change"].get("new_stage")

    if codegen_report.get("release_id") != spec["change_id"]:
        violations.append("codegen_report.release_id must match spec.change_id")

    if module_constants.get("SCHEMA_VERSION") != spec["schema_version"]:
        violations.append("generated code SCHEMA_VERSION mismatch")

    if module_constants.get("CHANGE_ID") != spec["change_id"]:
        violations.append("generated code CHANGE_ID mismatch")

    if module_constants.get("SERVICE") != spec["service"]:
        violations.append("generated code SERVICE mismatch")

    if module_constants.get("BASELINE_STAGES") != expected_baseline:
        violations.append("generated code BASELINE_STAGES mismatch")

    expected_new_stage_name = expected_new_stage["name"] if expected_new_stage else None
    expected_new_stage_threshold = (
        expected_new_stage["required_when"]["amount_gte"] if expected_new_stage else None
    )

    if module_constants.get("NEW_STAGE_NAME") != expected_new_stage_name:
        violations.append("generated code NEW_STAGE_NAME mismatch")

    if module_constants.get("NEW_STAGE_THRESHOLD") != expected_new_stage_threshold:
        violations.append("generated code NEW_STAGE_THRESHOLD mismatch")

    report = {
        "release_id": spec["change_id"],
        "spec": str(spec_path),
        "release_dir": str(release_dir),
        "status": "pass" if not violations else "fail",
        "violations": violations,
    }

    evidence_dir = release_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "code-policy-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    if violations:
        print("Generated code policy failed:")
        for v in violations:
            print(f"- {v}")
        raise SystemExit(1)

    print("Generated code policy passed")


if __name__ == "__main__":
    main()
