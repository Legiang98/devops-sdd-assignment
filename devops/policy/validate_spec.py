#!/usr/bin/env python3
"""Validate a resolved spec before generation starts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from devops.spec.specs import load_resolved_spec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a spec for feat/* workflow")
    parser.add_argument("--spec", required=True, help="Path to spec YAML")
    parser.add_argument(
        "--report-dir",
        help="Directory where spec validation evidence should be written",
    )
    return parser.parse_args()


def python_violations(spec: dict[str, object]) -> list[str]:
    violations: list[str] = []

    required_fields = (
        "schema_version",
        "change_id",
        "service",
        "workflow_change",
        "deployment",
        "docs",
        "quality",
    )
    for field in required_fields:
        if field not in spec or spec[field] in (None, "", []):
            violations.append(f"missing required field: {field}")

    if spec.get("schema_version") != "1.0.0":
        violations.append(f"unsupported schema_version: {spec.get('schema_version')}")

    workflow_change = spec.get("workflow_change")
    if not isinstance(workflow_change, dict):
        violations.append("workflow_change must be a mapping")
        return violations

    baseline_stages = workflow_change.get("baseline_stages")
    if not baseline_stages:
        violations.append("workflow_change.baseline_stages is required")
    elif len(baseline_stages) == 0:
        violations.append("workflow_change.baseline_stages must not be empty")

    quality = spec.get("quality")
    if not isinstance(quality, dict):
        violations.append("quality must be a mapping")
        return violations

    unit_tests = quality.get("unit_tests")
    if not isinstance(unit_tests, dict):
        violations.append("quality.unit_tests is required")
    else:
        if unit_tests.get("required") is not True:
            violations.append("quality.unit_tests.required must be true")
        min_new_tests = unit_tests.get("min_new_tests")
        if min_new_tests is None:
            violations.append("quality.unit_tests.min_new_tests is required")
        elif min_new_tests < 1:
            violations.append("quality.unit_tests.min_new_tests must be >= 1")

    docs = spec.get("docs")
    if not isinstance(docs, dict):
        violations.append("docs must be a mapping")
        return violations

    swagger = docs.get("swagger")
    if not isinstance(swagger, dict):
        violations.append("docs.swagger is required")
    elif not swagger.get("path") and not swagger.get("url"):
        violations.append("docs.swagger.path or docs.swagger.url is required")

    return violations


def opa_violations(spec: dict[str, object]) -> list[str]:
    if not shutil_which("opa"):
        return []

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        input_path = Path(handle.name)
        json.dump({"spec": spec}, handle)

    try:
        result = subprocess.run(
            [
                "opa",
                "eval",
                "--format=json",
                "-d",
                "devops/policy/spec_validation.rego",
                "-i",
                str(input_path),
                "data.policy.spec_validation.deny",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
    finally:
        input_path.unlink(missing_ok=True)

    try:
        values = payload["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return ["opa spec validation returned an unexpected response"]

    if isinstance(values, list):
        return [str(item) for item in values]
    return []


def shutil_which(command: str) -> str | None:
    probe = subprocess.run(
        ["which", command],
        capture_output=True,
        text=True,
        check=False,
    )
    value = probe.stdout.strip()
    return value or None


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = load_resolved_spec(spec_path)
    report_dir = Path(args.report_dir or f"build/releases/{spec['change_id']}/evidence")
    report_dir.mkdir(parents=True, exist_ok=True)

    violations: list[str] = []
    for violation in python_violations(spec):
        if violation not in violations:
            violations.append(violation)
    for violation in opa_violations(spec):
        if violation not in violations:
            violations.append(violation)

    report = {
        "spec": str(spec_path),
        "release_id": spec["change_id"],
        "status": "pass" if not violations else "fail",
        "violations": violations,
    }
    report_path = report_dir / "spec-validation-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if violations:
        print("Spec validation failed:")
        for violation in violations:
            print(f"- {violation}")
        raise SystemExit(1)

    print(f"Spec validation passed: {spec_path}")


if __name__ == "__main__":
    main()
