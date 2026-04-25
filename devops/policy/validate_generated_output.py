#!/usr/bin/env python3
"""Validate generated application output against the resolved spec."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from devops.spec.specs import load_resolved_spec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated application output")
    parser.add_argument("--spec", required=True, help="Path to spec YAML")
    parser.add_argument(
        "--report-dir",
        help="Optional directory where the report should be written",
    )
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


def route_map(module_path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    routes: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "app":
                continue
            if not decorator.args:
                continue
            first_arg = decorator.args[0]
            if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
                continue
            routes.add((func.attr.upper(), first_arg.value))
    return routes


def app_imports_contract(module_path: Path) -> bool:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "src.generated.spec_contract":
            return True
    return False


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = load_resolved_spec(spec_path)

    workspace = spec.get("workspace", {})
    app_root = Path(workspace.get("path", spec_path.resolve().parents[1])).resolve()
    source_root = app_root / workspace.get("src_path", "src")
    contract_path = source_root / "generated" / "spec_contract.py"
    app_main_path = source_root / "main.py"

    report_dir = Path(args.report_dir or f"build/policy/{spec['change_id']}")
    report_dir.mkdir(parents=True, exist_ok=True)

    violations: list[str] = []

    print(f"[policy] scan contract file: {contract_path}")
    if not contract_path.exists():
        violations.append(f"missing generated contract: {contract_path}")
    else:
        constants = extract_constants(contract_path)
        expected_baseline = [
            stage["name"] for stage in spec["workflow_change"]["baseline_stages"]
        ]
        expected_new_stage = spec["workflow_change"].get("new_stage")
        expected_new_stage_name = expected_new_stage["name"] if expected_new_stage else None
        expected_new_stage_threshold = (
            expected_new_stage["required_when"]["amount_gte"] if expected_new_stage else None
        )

        checks = [
            ("SCHEMA_VERSION", spec["schema_version"]),
            ("CHANGE_ID", spec["change_id"]),
            ("SERVICE", spec["service"]),
            ("BASELINE_STAGES", expected_baseline),
            ("NEW_STAGE_NAME", expected_new_stage_name),
            ("NEW_STAGE_THRESHOLD", expected_new_stage_threshold),
        ]
        for key, expected in checks:
            actual = constants.get(key)
            print(f"[policy] contract check {key}: expected={expected!r} actual={actual!r}")
            if actual != expected:
                violations.append(f"generated contract {key} mismatch")

    print(f"[policy] scan app entrypoint: {app_main_path}")
    if not app_main_path.exists():
        violations.append(f"missing app entrypoint: {app_main_path}")
    else:
        if not app_imports_contract(app_main_path):
            violations.append("generated app must import src.generated.spec_contract")

        actual_routes = route_map(app_main_path)
        expected_routes = {
            (str(endpoint["method"]).upper(), endpoint["path"])
            for endpoint in spec.get("api_contract", {}).get("endpoints", [])
        }
        expected_routes.update({("GET", "/health"), ("GET", "/metrics")})

        print("[policy] route scan start")
        for method, path in sorted(actual_routes):
            print(f"[policy] found route {method} {path}")
        for route in sorted(expected_routes):
            if route not in actual_routes:
                violations.append(f"generated app missing route {route[0]} {route[1]}")

        reject_expected = ("POST", "/expenses/{expense_id}/reject") in expected_routes
        has_reject = ("POST", "/expenses/{expense_id}/reject") in actual_routes
        print(f"[policy] reject route expected={reject_expected} actual={has_reject}")
        if has_reject != reject_expected:
            violations.append("generated app reject route does not match spec")

    report = {
        "release_id": spec["change_id"],
        "spec": str(spec_path),
        "app_root": str(app_root),
        "status": "pass" if not violations else "fail",
        "violations": violations,
    }
    report_path = report_dir / "generated-output-policy-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if violations:
        print("[policy] generated output validation failed")
        for violation in violations:
            print(f"[policy] violation: {violation}")
        raise SystemExit(1)

    print("[policy] generated output validation passed")


if __name__ == "__main__":
    main()
