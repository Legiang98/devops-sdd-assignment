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


def route_map(module_path: Path) -> dict[tuple[str, str], str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    routes: dict[tuple[str, str], str] = {}
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
            routes[(func.attr.upper(), first_arg.value)] = node.name
    return routes


def app_imports_contract(module_path: Path) -> bool:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "src.generated.spec_contract":
            return True
    return False


def yaml_doc(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise SystemExit(f"Expected mapping YAML in {path}")
    return parsed


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    release_dir = Path(args.release_dir)

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    codegen_report_path = release_dir / "evidence" / "codegen-report.json"
    codegen_report = json.loads(codegen_report_path.read_text(encoding="utf-8"))
    workspace = spec.get("workspace", {})
    manifest_path_str = workspace.get("manifest_path", f"devops/k8s/{spec_path.resolve().parents[1].name}")
    app_root = Path(workspace.get("path", spec_path.resolve().parents[1])).resolve()
    manifest_root = Path(manifest_path_str).resolve()
    argocd_root = Path("devops/k8s/argocd").resolve()
    argocd_config = ((spec.get("gitops") or {}).get("argocd") or {})
    argocd_enabled = argocd_config.get("enabled", True)
    argocd_application_name = argocd_config.get("application_name", app_root.name)
    argocd_application_path = argocd_root / f"{app_root.name}-application.yaml"
    dockerfile_path = app_root / workspace.get("dockerfile_path", "Dockerfile")
    tests_root = app_root / workspace.get("tests_path", "tests")

    module_path = Path(codegen_report["module_path"])
    module_constants = extract_constants(module_path)
    app_module_path = Path(
        codegen_report.get("app_module_path", app_root / "src" / "main.py")
    ).resolve()
    generated_files = [Path(p).resolve() for p in codegen_report.get("generated_files", [])]

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

    expected_generated = {
        app_root / "src" / "generated" / "spec_contract.py",
        app_root / "src" / "__init__.py",
        app_root / "src" / "main.py",
        app_root / "README.md",
        app_root / "src" / "README.md",
        dockerfile_path,
        tests_root / "README.md",
        tests_root / "test_generated_placeholder.py",
        manifest_root / "namespace.yaml",
        manifest_root / "deployment.yaml",
        manifest_root / "service.yaml",
        manifest_root / "ingress.yaml",
    }
    if argocd_enabled:
        expected_generated.add(argocd_application_path)
    missing_generated = [str(path) for path in expected_generated if path not in generated_files]
    if missing_generated:
        violations.append(
            f"generated_files missing expected outputs: {', '.join(sorted(missing_generated))}"
        )

    for path in generated_files:
        if (
            not is_within(path, app_root)
            and not is_within(path, manifest_root)
            and not is_within(path, argocd_root)
        ):
            violations.append(f"generated file outside app/gitops scope: {path}")

    if not app_module_path.exists():
        violations.append(f"generated app module missing: {app_module_path}")
    else:
        if not app_imports_contract(app_module_path):
            violations.append("generated app must import src.generated.spec_contract")

        actual_routes = route_map(app_module_path)
        expected_routes = {
            (str(endpoint["method"]).upper(), endpoint["path"])
            for endpoint in spec.get("api_contract", {}).get("endpoints", [])
        }
        expected_routes.update({("GET", "/health"), ("GET", "/metrics")})
        for route in sorted(expected_routes):
            if route not in actual_routes:
                violations.append(f"generated app missing route {route[0]} {route[1]}")

        has_reject = ("POST", "/expenses/{expense_id}/reject") in actual_routes
        reject_expected = any(
            str(endpoint["method"]).upper() == "POST"
            and endpoint["path"] == "/expenses/{expense_id}/reject"
            for endpoint in spec.get("api_contract", {}).get("endpoints", [])
        )
        if has_reject != reject_expected:
            violations.append("generated app reject route does not match spec")

    if not dockerfile_path.exists():
        violations.append(f"generated Dockerfile missing: {dockerfile_path}")

    if not tests_root.exists():
        violations.append(f"generated tests directory missing: {tests_root}")

    namespace_path = manifest_root / "namespace.yaml"
    deployment_path = manifest_root / "deployment.yaml"
    service_path = manifest_root / "service.yaml"
    ingress_path = manifest_root / "ingress.yaml"
    k8s = spec["deployment"]["k8s"]

    if not namespace_path.exists():
        violations.append(f"missing manifest: {namespace_path}")
    else:
        namespace_doc = yaml_doc(namespace_path)
        if namespace_doc is not None and namespace_doc.get("metadata", {}).get("name") != k8s["namespace"]:
            violations.append("namespace manifest name mismatch")

    if not deployment_path.exists():
        violations.append(f"missing manifest: {deployment_path}")
    else:
        deployment_doc = yaml_doc(deployment_path)
        container = (
            deployment_doc.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [{}])[0]
        )
        if deployment_doc.get("metadata", {}).get("name") != k8s["deployment"]["name"]:
            violations.append("deployment manifest name mismatch")
        if deployment_doc.get("metadata", {}).get("namespace") != k8s["namespace"]:
            violations.append("deployment manifest namespace mismatch")
        if deployment_doc.get("spec", {}).get("replicas") != k8s["deployment"]["replicas"]:
            violations.append("deployment replicas mismatch")
        port = (container.get("ports") or [{}])[0].get("containerPort")
        if port != k8s["deployment"]["container_port"]:
            violations.append("deployment container_port mismatch")
        if not container.get("image"):
            violations.append("deployment image is required")

    if not service_path.exists():
        violations.append(f"missing manifest: {service_path}")
    else:
        service_doc = yaml_doc(service_path)
        service_port = (service_doc.get("spec", {}).get("ports") or [{}])[0]
        if service_doc.get("metadata", {}).get("name") != k8s["service"]["name"]:
            violations.append("service manifest name mismatch")
        if service_doc.get("metadata", {}).get("namespace") != k8s["namespace"]:
            violations.append("service manifest namespace mismatch")
        if service_port.get("port") != k8s["service"]["port"]:
            violations.append("service port mismatch")
        if service_port.get("targetPort") != k8s["service"]["target_port"]:
            violations.append("service targetPort mismatch")

    ingress_enabled = k8s.get("ingress", {}).get("enabled", False)
    if not ingress_path.exists():
        violations.append(f"missing manifest: {ingress_path}")
    else:
        ingress_text = ingress_path.read_text(encoding="utf-8")
        if ingress_enabled:
            ingress_doc = yaml_doc(ingress_path)
            if ingress_doc is None or ingress_doc.get("kind") != "Ingress":
                violations.append("ingress manifest must be a Kubernetes Ingress when enabled")
            else:
                rules = ingress_doc.get("spec", {}).get("rules") or []
                if not rules:
                    violations.append("ingress rules are required when ingress is enabled")
                backend_service = (
                    rules[0]
                    .get("http", {})
                    .get("paths", [{}])[0]
                    .get("backend", {})
                    .get("service", {})
                )
                if backend_service.get("name") != k8s["service"]["name"]:
                    violations.append("ingress backend service mismatch")
        else:
            if "Ingress disabled by spec." not in ingress_text:
                violations.append("ingress manifest must stay disabled when spec ingress.enabled is false")

    if argocd_enabled:
        if not argocd_application_path.exists():
            violations.append(f"missing Argo CD application manifest: {argocd_application_path}")
        else:
            argocd_doc = yaml_doc(argocd_application_path)
            metadata = (argocd_doc or {}).get("metadata", {}) or {}
            argocd_spec = (argocd_doc or {}).get("spec", {}) or {}
            source = argocd_spec.get("source", {}) or {}
            destination = argocd_spec.get("destination", {}) or {}
            expected_source_path = Path(manifest_path_str).as_posix()

            if (argocd_doc or {}).get("kind") != "Application":
                violations.append("Argo CD manifest kind must be Application")
            if metadata.get("namespace") != "argocd":
                violations.append("Argo CD application namespace must be argocd")
            if metadata.get("name") != argocd_application_name:
                violations.append("Argo CD application metadata.name mismatch")
            if argocd_application_path.name != f"{app_root.name}-application.yaml":
                violations.append("Argo CD application filename mismatch")
            if source.get("path") != expected_source_path:
                violations.append("Argo CD application source.path must match spec.workspace.manifest_path")
            if destination.get("namespace") != k8s["namespace"]:
                violations.append("Argo CD application destination namespace mismatch")
    elif codegen_report.get("argocd_application_path"):
        violations.append("Argo CD application must not be generated when spec disables it")

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
