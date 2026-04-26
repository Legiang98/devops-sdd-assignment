#!/usr/bin/env python3
"""Validate BASELINE.yaml for deterministic GitOps scaffold generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate baseline spec for GitOps generation")
    parser.add_argument("--spec", required=True, help="Path to changed spec YAML")
    parser.add_argument(
        "--report-dir",
        help="Directory where baseline validation evidence should be written",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected mapping YAML in {path}")
    return payload


def find_baseline(app_root: Path) -> Path:
    specs_dir = app_root / "specs"
    exact = specs_dir / "BASELINE.yaml"
    if exact.exists():
        return exact

    candidates = sorted(specs_dir.glob("*BASELINE*.y*ml"))
    if candidates:
        return candidates[0]

    raise SystemExit(f"No baseline spec found under {specs_dir}")


def infer_workspace_path(app_root: Path) -> str:
    try:
        return app_root.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        parts = app_root.parts
        if "applications" in parts:
            idx = parts.index("applications")
            return Path(*parts[idx:]).as_posix()
        return app_root.as_posix()


def validate_baseline(baseline: dict, baseline_path: Path, app_root: Path) -> list[str]:
    violations: list[str] = []

    required_top_level = (
        "schema_version",
        "change_id",
        "service",
        "workflow_change",
        "deployment",
        "docs",
        "quality",
    )
    for field in required_top_level:
        if field not in baseline or baseline[field] in (None, "", []):
            violations.append(f"missing required field: {field}")

    if baseline.get("schema_version") != "1.0.0":
        violations.append(f"unsupported schema_version: {baseline.get('schema_version')}")

    workspace = baseline.get("workspace")
    if not isinstance(workspace, dict):
        violations.append("workspace is required for deterministic baseline generation")
        workspace = {}

    expected_workspace_path = infer_workspace_path(app_root)
    actual_workspace_path = str(workspace.get("path", "")).rstrip("/")
    if actual_workspace_path != expected_workspace_path:
        violations.append(
            f"workspace.path must be {expected_workspace_path}"
        )

    expected_manifest_path = f"devops/k8s/{app_root.name}"
    if workspace.get("manifest_path") != expected_manifest_path:
        violations.append(
            f"workspace.manifest_path must be {expected_manifest_path}"
        )

    for field, expected_value in (
        ("src_path", "src"),
        ("tests_path", "tests"),
        ("dockerfile_path", "Dockerfile"),
    ):
        if workspace.get(field) != expected_value:
            violations.append(f"workspace.{field} must be {expected_value}")

    workflow_change = baseline.get("workflow_change")
    if not isinstance(workflow_change, dict):
        violations.append("workflow_change must be a mapping")
    elif not workflow_change.get("baseline_stages"):
        violations.append("workflow_change.baseline_stages is required")

    docs = baseline.get("docs")
    if not isinstance(docs, dict):
        violations.append("docs must be a mapping")
    else:
        swagger = docs.get("swagger")
        if not isinstance(swagger, dict):
            violations.append("docs.swagger is required")
        elif not swagger.get("path") and not swagger.get("url"):
            violations.append("docs.swagger.path or docs.swagger.url is required")

    quality = baseline.get("quality")
    if not isinstance(quality, dict):
        violations.append("quality must be a mapping")
    else:
        unit_tests = quality.get("unit_tests")
        if not isinstance(unit_tests, dict):
            violations.append("quality.unit_tests is required")
        else:
            if unit_tests.get("required") is not True:
                violations.append("quality.unit_tests.required must be true")
            min_new_tests = unit_tests.get("min_new_tests")
            if not isinstance(min_new_tests, int) or min_new_tests < 1:
                violations.append("quality.unit_tests.min_new_tests must be an integer >= 1")

    deployment = baseline.get("deployment")
    if not isinstance(deployment, dict):
        violations.append("deployment must be a mapping")
        return violations

    k8s = deployment.get("k8s")
    if not isinstance(k8s, dict):
        violations.append("deployment.k8s is required")
        return violations

    namespace = k8s.get("namespace")
    if not isinstance(namespace, str) or not namespace.strip():
        violations.append("deployment.k8s.namespace is required")

    deployment_spec = k8s.get("deployment")
    if not isinstance(deployment_spec, dict):
        violations.append("deployment.k8s.deployment is required")
    else:
        if not deployment_spec.get("name"):
            violations.append("deployment.k8s.deployment.name is required")
        replicas = deployment_spec.get("replicas")
        if not isinstance(replicas, int) or replicas < 1:
            violations.append("deployment.k8s.deployment.replicas must be an integer >= 1")
        container_port = deployment_spec.get("container_port")
        if not isinstance(container_port, int) or container_port < 1:
            violations.append("deployment.k8s.deployment.container_port must be an integer >= 1")

    service_spec = k8s.get("service")
    if not isinstance(service_spec, dict):
        violations.append("deployment.k8s.service is required")
    else:
        if not service_spec.get("name"):
            violations.append("deployment.k8s.service.name is required")
        for field in ("port", "target_port"):
            value = service_spec.get(field)
            if not isinstance(value, int) or value < 1:
                violations.append(f"deployment.k8s.service.{field} must be an integer >= 1")

    ingress_spec = k8s.get("ingress", {})
    if ingress_spec is None:
        ingress_spec = {}
    if not isinstance(ingress_spec, dict):
        violations.append("deployment.k8s.ingress must be a mapping when present")
    else:
        enabled = ingress_spec.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            violations.append("deployment.k8s.ingress.enabled must be a boolean when present")

    return violations


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    app_root = spec_path.parent.parent
    baseline_path = find_baseline(app_root)
    baseline = load_yaml(baseline_path)

    report_dir = Path(args.report_dir or f"build/releases/{baseline.get('change_id', 'BASELINE')}/evidence")
    report_dir.mkdir(parents=True, exist_ok=True)

    violations = validate_baseline(baseline, baseline_path, app_root)
    report = {
        "spec": str(spec_path),
        "baseline": str(baseline_path),
        "status": "pass" if not violations else "fail",
        "violations": violations,
    }
    report_path = report_dir / "baseline-validation-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if violations:
        print("Baseline validation failed:")
        for violation in violations:
            print(f"- {violation}")
        raise SystemExit(1)

    print(f"Baseline validation passed: {baseline_path}")


if __name__ == "__main__":
    main()
