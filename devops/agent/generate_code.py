#!/usr/bin/env python
"""Generate application code artifacts from spec (deterministic or ollama-backed)."""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib import error, request

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from devops.specs import load_resolved_spec

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate code artifacts from a change spec")
    parser.add_argument("--spec", required=True, help="Path to YAML spec")
    parser.add_argument("--output-root", default="build/releases", help="Release root")
    parser.add_argument(
        "--provider",
        choices=["deterministic", "ollama"],
        default="deterministic",
        help="Code generation backend",
    )
    parser.add_argument(
        "--ollama-model",
        default="qwen2.5:7b",
        help="Ollama model name",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
        help="Ollama base URL",
    )
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=60,
        help="Ollama request timeout in seconds",
    )
    return parser.parse_args()


def expected_contract(spec: dict) -> dict[str, object]:
    baseline_stages = spec["workflow_change"]["baseline_stages"]
    baseline_stage_names = [stage["name"] for stage in baseline_stages]
    new_stage = spec["workflow_change"].get("new_stage")

    endpoints: list[str] = []
    for endpoint in spec.get("api_contract", {}).get("endpoints", []):
        method = str(endpoint.get("method", "")).upper()
        path = str(endpoint.get("path", ""))
        endpoints.append(f"{method} {path}")

    return {
        "schema_version": spec["schema_version"],
        "change_id": spec["change_id"],
        "service": spec["service"],
        "baseline_stage_names": baseline_stage_names,
        "new_stage_name": new_stage["name"] if new_stage else None,
        "new_stage_threshold": (
            new_stage["required_when"]["amount_gte"] if new_stage else None
        ),
        "api_endpoints": endpoints,
        "reject_endpoint_enabled": any(
            e == "POST /expenses/{expense_id}/reject" for e in endpoints
        ),
    }


def module_body_from_contract(contract: dict[str, object]) -> str:
    lines = [
        '"""Auto-generated from spec. Do not edit manually."""',
        "",
        f'SCHEMA_VERSION = {repr(contract["schema_version"])}',
        f'CHANGE_ID = {repr(contract["change_id"])}',
        f'SERVICE = {repr(contract["service"])}',
        f'BASELINE_STAGES = {repr(contract["baseline_stage_names"])}',
    ]

    if contract["new_stage_name"] is not None:
        lines.append(f'NEW_STAGE_NAME = {repr(contract["new_stage_name"])}')
        lines.append(f'NEW_STAGE_THRESHOLD = {repr(contract["new_stage_threshold"])}')
    else:
        lines.append("NEW_STAGE_NAME = None")
        lines.append("NEW_STAGE_THRESHOLD = None")

    lines.append(f'API_ENDPOINTS = {repr(contract["api_endpoints"])}')
    lines.append(f'REJECT_ENDPOINT_ENABLED = {repr(contract["reject_endpoint_enabled"])}')
    lines.append("")
    return "\n".join(lines)


def app_module_body_from_contract(contract: dict[str, object]) -> str:
    expense_lookup_enabled = "GET /expenses/{expense_id}" in contract["api_endpoints"]
    reject_enabled = "True" if contract["reject_endpoint_enabled"] else "False"
    lookup_route = ""
    if expense_lookup_enabled:
        lookup_route = '''


@app.get("/expenses/{expense_id}")
def get_expense(expense_id: str) -> dict[str, Any]:
    expense = EXPENSES.get(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return expense
'''
    reject_route = ""
    if contract["reject_endpoint_enabled"]:
        reject_route = '''


@app.post("/expenses/{expense_id}/reject")
def reject_expense(expense_id: str, req: RejectExpenseRequest) -> dict[str, Any]:
    if not REJECT_ENDPOINT_ENABLED:
        raise HTTPException(status_code=404, detail="Reject endpoint not enabled by spec")

    expense = EXPENSES.get(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if req.reason_code is None or req.comment is None:
        rejection_missing_reason_total.inc()
        raise HTTPException(
            status_code=400,
            detail="reason_code and comment are required for rejection",
        )

    expense["status"] = "REJECTED"
    expense["rejected_by"] = req.role
    expense["reason_code"] = req.reason_code
    expense["comment"] = req.comment

    expense_rejected_total.inc()
    audit(
        "expense_rejected",
        {
            "expense_id": expense_id,
            "rejected_by": req.role,
            "reason_code": req.reason_code,
        },
    )

    return expense
'''
    return f'''"""Auto-generated service module from spec. Do not edit manually."""

import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from src.generated.spec_contract import (
    BASELINE_STAGES,
    CHANGE_ID,
    NEW_STAGE_NAME,
    NEW_STAGE_THRESHOLD,
    SCHEMA_VERSION,
    SERVICE,
)

RULES_PATH = os.getenv("RULES_PATH", "deploy/current/rules.json")
RELEASE_ID_FILE = os.getenv("RELEASE_ID_FILE", "deploy/current/release_id.txt")
REJECT_ENDPOINT_ENABLED = {reject_enabled}

app = FastAPI(title="Expense Workflow Service")

expense_submitted_total = Counter("expense_submitted_total", "Submitted expenses")
approval_step_required_total = Counter(
    "approval_step_required_total", "Required approvals by step", ["step"]
)
approval_step_completed_total = Counter(
    "approval_step_completed_total", "Completed approvals by step", ["step"]
)
expense_approved_total = Counter("expense_approved_total", "Fully approved expenses")
expense_rejected_total = Counter("expense_rejected_total", "Rejected expenses")
rejection_missing_reason_total = Counter(
    "rejection_missing_reason_total", "Rejected requests missing reason fields"
)

EXPENSES: dict[str, dict[str, Any]] = {{}}


def setup_tracing() -> None:
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        return

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4318",
    ).rstrip("/")
    service_name = os.getenv("OTEL_SERVICE_NAME", SERVICE)

    resource = Resource.create(
        {{
            "service.name": service_name,
            "spec.schema_version": SCHEMA_VERSION,
            "spec.change_id": CHANGE_ID,
        }}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{{endpoint}}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


class SubmitExpenseRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str


class ApproveExpenseRequest(BaseModel):
    role: str


class RejectExpenseRequest(BaseModel):
    role: str
    reason_code: str | None = None
    comment: str | None = None


def read_release_id() -> str:
    try:
        with open(RELEASE_ID_FILE, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return value or CHANGE_ID
    except FileNotFoundError:
        return CHANGE_ID


def load_rules() -> dict[str, Any]:
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        stages = [{{"name": s, "required_when": {{"amount_gte": 0}}}} for s in BASELINE_STAGES]
        if NEW_STAGE_NAME is not None:
            stages.append(
                {{
                    "name": NEW_STAGE_NAME,
                    "required_when": {{
                        "amount_gte": 0 if NEW_STAGE_THRESHOLD is None else NEW_STAGE_THRESHOLD
                    }},
                }}
            )
        return {{"workflow": {{"stages": stages}}}}


def required_stages_for_amount(amount: float, rules: dict[str, Any]) -> list[str]:
    stages = []
    for stage in rules["workflow"]["stages"]:
        threshold = float(stage["required_when"]["amount_gte"])
        if amount >= threshold:
            stages.append(stage["name"])
    return stages


def audit(event: str, payload: dict[str, Any]) -> None:
    log_line = {{
        "ts": int(time.time()),
        "release_id": read_release_id(),
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "event": event,
        "payload": payload,
    }}
    print(json.dumps(log_line), flush=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {{
        "status": "ok",
        "release_id": read_release_id(),
        "change_id": CHANGE_ID,
        "service": SERVICE,
    }}


@app.post("/expenses")
def submit_expense(req: SubmitExpenseRequest) -> dict[str, Any]:
    rules = load_rules()
    stages = required_stages_for_amount(req.amount, rules)

    expense_id = str(uuid.uuid4())
    EXPENSES[expense_id] = {{
        "id": expense_id,
        "amount": req.amount,
        "description": req.description,
        "required_stages": stages,
        "approved_stages": [],
        "status": "PENDING_APPROVAL",
    }}

    expense_submitted_total.inc()
    for step in stages:
        approval_step_required_total.labels(step=step).inc()

    audit(
        "expense_submitted",
        {{
            "expense_id": expense_id,
            "amount": req.amount,
            "required_stages": stages,
        }},
    )

    return EXPENSES[expense_id]


@app.post("/expenses/{{expense_id}}/approve")
def approve_expense(expense_id: str, req: ApproveExpenseRequest) -> dict[str, Any]:
    expense = EXPENSES.get(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if expense["status"] == "REJECTED":
        raise HTTPException(status_code=400, detail="Expense already rejected")

    if req.role not in expense["required_stages"]:
        raise HTTPException(status_code=400, detail=f"Role {{req.role}} is not required")

    if req.role in expense["approved_stages"]:
        return expense

    expense["approved_stages"].append(req.role)
    approval_step_completed_total.labels(step=req.role).inc()

    if set(expense["approved_stages"]) == set(expense["required_stages"]):
        expense["status"] = "APPROVED"
        expense_approved_total.inc()

    audit(
        "expense_approved_step",
        {{
            "expense_id": expense_id,
            "approved_role": req.role,
            "status": expense["status"],
        }},
    )

    return expense


{lookup_route}

{reject_route}

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


setup_tracing()
'''


def generic_app_module_body(contract: dict[str, object], app_title: str) -> str:
    endpoint_defs: list[str] = []
    for index, endpoint in enumerate(contract["api_endpoints"]):
        method, path = endpoint.split(" ", 1)
        method_lower = method.lower()
        fn_name = f"endpoint_{index}"
        if "{" in path:
            fn_name = f"{fn_name}_path"
        path_params = re.findall(r"{([^}]+)}", path)
        path_args = ", ".join(f"{param}: str" for param in path_params)
        path_payload = ", ".join(f'"{param}": {param}' for param in path_params)
        if path_payload:
            path_payload = f", \"path_params\": {{{path_payload}}}"
        if method == "GET":
            body = f"""
@app.get("{path}")
def {fn_name}({path_args}) -> dict[str, object]:
    return {{
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "method": "{method}",
        "path": "{path}",
        "message": "Generated endpoint placeholder"{path_payload},
    }}
"""
        else:
            args = path_args
            if args:
                args = f"{args}, payload: dict[str, object] | None = None"
            else:
                args = "payload: dict[str, object] | None = None"
            body = f"""
@app.{method_lower}("{path}")
def {fn_name}({args}) -> dict[str, object]:
    return {{
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "method": "{method}",
        "path": "{path}",
        "payload": payload or {{}},
        "message": "Generated endpoint placeholder"{path_payload},
    }}
"""
        endpoint_defs.append(body.strip("\n"))

    endpoint_block = "\n\n".join(endpoint_defs)
    return f'''"""Auto-generated service module from spec. Do not edit manually."""

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from src.generated.spec_contract import (
    API_ENDPOINTS,
    BASELINE_STAGES,
    CHANGE_ID,
    NEW_STAGE_NAME,
    NEW_STAGE_THRESHOLD,
    REJECT_ENDPOINT_ENABLED,
    SCHEMA_VERSION,
    SERVICE,
)

app = FastAPI(title="{app_title}")

request_total = Counter("generated_request_total", "Generated placeholder requests", ["method", "path"])


@app.get("/health")
def health() -> dict[str, object]:
    return {{
        "status": "ok",
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "schema_version": SCHEMA_VERSION,
        "baseline_stages": BASELINE_STAGES,
        "new_stage_name": NEW_STAGE_NAME,
        "new_stage_threshold": NEW_STAGE_THRESHOLD,
        "reject_endpoint_enabled": REJECT_ENDPOINT_ENABLED,
        "api_endpoints": API_ENDPOINTS,
    }}


{endpoint_block}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
'''


def dockerfile_body(app_dir_name: str) -> str:
    return (
        "FROM python:3.12-slim\n\n"
        "WORKDIR /app\n\n"
        "COPY requirements.txt /app/requirements.txt\n"
        "RUN pip install --no-cache-dir -r /app/requirements.txt\n\n"
        f"COPY applications/{app_dir_name}/src /app/src\n\n"
        'CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
    )


def service_readme_body(app_dir_name: str) -> str:
    title = app_dir_name.replace("-", " ").title()
    return (
        f"# {title}\n\n"
        "Business application slice generated from spec.\n\n"
        "- `specs/`: versioned change specifications\n"
        "- `src/`: service implementation\n"
        "- `tests/`: service tests\n"
    )


def src_readme_body() -> str:
    return "# Service Source\n\nRuntime service code for the generated application.\n"


def tests_readme_body() -> str:
    return "# Tests Placeholder\n\nAdd service-level tests for behavior described in specs.\n"


def tests_module_body(app_dir_name: str) -> str:
    return (
        f'"""Placeholder tests for {app_dir_name}.\n\n'
        "Replace with behavior tests that validate spec-driven output.\n"
        '"""\n\n\n'
        "def test_placeholder() -> None:\n"
        "    assert True\n"
    )


def namespace_manifest_from_spec(spec: dict) -> str:
    namespace = spec["deployment"]["k8s"]["namespace"]
    return (
        "apiVersion: v1\n"
        "kind: Namespace\n"
        "metadata:\n"
        f"  name: {namespace}\n"
    )


def deployment_manifest_from_spec(spec: dict, image_repository: str) -> str:
    k8s = spec["deployment"]["k8s"]
    deployment = k8s["deployment"]
    service = spec["service"]
    return (
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        f"  name: {deployment['name']}\n"
        f"  namespace: {k8s['namespace']}\n"
        "  labels:\n"
        f"    app: {service}\n"
        "spec:\n"
        f"  replicas: {deployment['replicas']}\n"
        "  selector:\n"
        "    matchLabels:\n"
        f"      app: {service}\n"
        "  template:\n"
        "    metadata:\n"
        "      labels:\n"
        f"        app: {service}\n"
        "    spec:\n"
        "      containers:\n"
        "        - name: app\n"
        f"          image: {image_repository}:latest\n"
        "          imagePullPolicy: IfNotPresent\n"
        "          ports:\n"
        f"            - containerPort: {deployment['container_port']}\n"
        "              name: http\n"
        "          env:\n"
        "            - name: RULES_PATH\n"
        "              value: /runtime/rules.json\n"
        "            - name: RELEASE_ID_FILE\n"
        "              value: /runtime/release_id.txt\n"
        "            - name: OTEL_EXPORTER_OTLP_ENDPOINT\n"
        "              value: http://alloy.monitoring.svc.cluster.local:4318\n"
        "            - name: OTEL_SERVICE_NAME\n"
        f"              value: {service}\n"
    )


def service_manifest_from_spec(spec: dict) -> str:
    k8s = spec["deployment"]["k8s"]
    service = k8s["service"]
    app_label = spec["service"]
    return (
        "apiVersion: v1\n"
        "kind: Service\n"
        "metadata:\n"
        f"  name: {service['name']}\n"
        f"  namespace: {k8s['namespace']}\n"
        "spec:\n"
        "  selector:\n"
        f"    app: {app_label}\n"
        "  ports:\n"
        "    - name: http\n"
        "      protocol: TCP\n"
        f"      port: {service['port']}\n"
        f"      targetPort: {service['target_port']}\n"
    )


def ingress_host_for_app(app_dir_name: str) -> str:
    return f"{app_dir_name}.192.168.49.2.nip.io"


def ingress_manifest_from_spec(spec: dict, app_dir_name: str) -> str:
    k8s = spec["deployment"]["k8s"]
    service = k8s["service"]
    ingress_enabled = k8s.get("ingress", {}).get("enabled", False)
    host = ingress_host_for_app(app_dir_name)

    if not ingress_enabled:
        return (
            "# Ingress disabled by spec.\n"
            f"# If enabled later, use host http://{host}\n"
        )

    return (
        "apiVersion: networking.k8s.io/v1\n"
        "kind: Ingress\n"
        "metadata:\n"
        f"  name: {service['name']}\n"
        f"  namespace: {k8s['namespace']}\n"
        "  annotations:\n"
        "    nginx.ingress.kubernetes.io/rewrite-target: /\n"
        "spec:\n"
        "  ingressClassName: nginx\n"
        "  rules:\n"
        f"    - host: {host}\n"
        "      http:\n"
        "        paths:\n"
        "          - path: /\n"
        "            pathType: Prefix\n"
        "            backend:\n"
        "              service:\n"
        f"                name: {service['name']}\n"
        "                port:\n"
        f"                  number: {service['port']}\n"
    )


def argocd_config_from_spec(spec: dict, app_dir_name: str) -> dict[str, object]:
    argocd = ((spec.get("gitops") or {}).get("argocd") or {})
    return {
        "enabled": argocd.get("enabled", True),
        "application_name": argocd.get("application_name", app_dir_name),
        "project": argocd.get("project", "default"),
    }


def repo_url_for_argocd() -> str:
    repo_secret_path = Path("devops/k8s/argocd/repo-secret.yaml")
    if repo_secret_path.exists():
        repo_secret = yaml.safe_load(repo_secret_path.read_text(encoding="utf-8")) or {}
        secret_url = ((repo_secret.get("stringData") or {}).get("url") or "").strip()
        if secret_url:
            return secret_url

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""

    return result.stdout.strip()


def argocd_application_manifest_from_spec(
    spec: dict,
    app_dir_name: str,
    manifest_path: str,
) -> str:
    config = argocd_config_from_spec(spec, app_dir_name)
    repo_url = repo_url_for_argocd()
    manifest_path_str = manifest_path.replace("\\", "/")
    lines = [
        "apiVersion: argoproj.io/v1alpha1",
        "kind: Application",
        "metadata:",
        f"  name: {config['application_name']}",
        "  namespace: argocd",
        "spec:",
        "  destination:",
        f"    namespace: {spec['deployment']['k8s']['namespace']}",
        "    server: https://kubernetes.default.svc",
        f"  project: {config['project']}",
        "  source:",
        f"    path: {manifest_path_str}",
        f"    repoURL: {repo_url}",
        "    targetRevision: HEAD",
        "  syncPolicy:",
        "    automated:",
        "      prune: true",
        "      selfHeal: true",
        "    syncOptions:",
        "    - CreateNamespace=true",
    ]
    return "\n".join(lines) + "\n"


def parse_json_object(response_text: str) -> dict[str, str]:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Ollama returned invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit("Ollama bundle response must be a JSON object")

    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise SystemExit("Ollama bundle keys and values must be strings")
    return data


def route_map_from_source(module_source: str) -> dict[tuple[str, str], str]:
    tree = ast.parse(module_source)
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


def validate_app_source_against_spec(app_source: str, spec: dict) -> list[str]:
    violations: list[str] = []
    if "from src.generated.spec_contract import" not in app_source:
        violations.append("generated app must import src.generated.spec_contract")
        return violations

    try:
        routes = route_map_from_source(app_source)
    except SyntaxError as exc:
        return [f"generated app source is invalid Python: {exc}"]

    expected_routes = {
        (str(endpoint["method"]).upper(), endpoint["path"])
        for endpoint in spec.get("api_contract", {}).get("endpoints", [])
    }
    expected_routes.update({("GET", "/health"), ("GET", "/metrics")})
    for route in sorted(expected_routes):
        if route not in routes:
            violations.append(f"generated app missing route {route[0]} {route[1]}")

    reject_expected = any(
        str(endpoint["method"]).upper() == "POST"
        and endpoint["path"] == "/expenses/{expense_id}/reject"
        for endpoint in spec.get("api_contract", {}).get("endpoints", [])
    )
    has_reject = ("POST", "/expenses/{expense_id}/reject") in routes
    if has_reject != reject_expected:
        violations.append("generated app reject route does not match spec")
    return violations


def summarize_manifests(
    namespace_source: str,
    deployment_source: str,
    service_source: str,
    ingress_source: str,
) -> dict[str, object]:
    namespace_doc = yaml.safe_load(namespace_source) if namespace_source.strip() else None
    deployment_doc = yaml.safe_load(deployment_source) if deployment_source.strip() else None
    service_doc = yaml.safe_load(service_source) if service_source.strip() else None
    ingress_summary: dict[str, object]

    if ingress_source.lstrip().startswith("#"):
        ingress_summary = {"enabled": False, "kind": None, "host": None, "backend_service": None}
    else:
        ingress_doc = yaml.safe_load(ingress_source) if ingress_source.strip() else None
        rules = ((ingress_doc or {}).get("spec", {}) or {}).get("rules") or []
        backend_service = None
        host = None
        if rules:
            host = rules[0].get("host")
            backend_service = (
                rules[0]
                .get("http", {})
                .get("paths", [{}])[0]
                .get("backend", {})
                .get("service", {})
                .get("name")
            )
        ingress_summary = {
            "enabled": True,
            "kind": (ingress_doc or {}).get("kind"),
            "host": host,
            "backend_service": backend_service,
        }

    deployment_container = (
        ((deployment_doc or {}).get("spec", {}) or {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [{}])[0]
    )
    service_port = (((service_doc or {}).get("spec", {}) or {}).get("ports") or [{}])[0]

    return {
        "namespace": {
            "name": ((namespace_doc or {}).get("metadata", {}) or {}).get("name"),
        },
        "deployment": {
            "name": ((deployment_doc or {}).get("metadata", {}) or {}).get("name"),
            "namespace": ((deployment_doc or {}).get("metadata", {}) or {}).get("namespace"),
            "replicas": ((deployment_doc or {}).get("spec", {}) or {}).get("replicas"),
            "container_port": deployment_container.get("ports", [{}])[0].get("containerPort")
            if deployment_container.get("ports")
            else None,
            "image": deployment_container.get("image"),
        },
        "service": {
            "name": ((service_doc or {}).get("metadata", {}) or {}).get("name"),
            "namespace": ((service_doc or {}).get("metadata", {}) or {}).get("namespace"),
            "port": service_port.get("port"),
            "target_port": service_port.get("targetPort"),
        },
        "ingress": ingress_summary,
    }


def summarize_argocd_application(application_source: str) -> dict[str, object] | None:
    if not application_source.strip():
        return None

    application_doc = yaml.safe_load(application_source)
    if not isinstance(application_doc, dict):
        return None

    source = (application_doc.get("spec", {}) or {}).get("source", {}) or {}
    destination = (application_doc.get("spec", {}) or {}).get("destination", {}) or {}
    return {
        "name": ((application_doc.get("metadata", {}) or {}).get("name")),
        "namespace": ((application_doc.get("metadata", {}) or {}).get("namespace")),
        "project": ((application_doc.get("spec", {}) or {}).get("project")),
        "source_path": source.get("path"),
        "repo_url": source.get("repoURL"),
        "target_revision": source.get("targetRevision"),
        "destination_namespace": destination.get("namespace"),
        "destination_server": destination.get("server"),
    }


def render_contract_prompt(contract: dict[str, object]) -> str:
    system_prompt = (PROMPTS_DIR / "codegen_system.txt").read_text(encoding="utf-8").strip()
    user_template = (PROMPTS_DIR / "codegen_user_template.txt").read_text(encoding="utf-8")
    user_prompt = user_template.format(
        schema_version_json=json.dumps(contract["schema_version"]),
        change_id_json=json.dumps(contract["change_id"]),
        service_json=json.dumps(contract["service"]),
        baseline_stages_json=json.dumps(contract["baseline_stage_names"]),
        new_stage_name_json=json.dumps(contract["new_stage_name"]),
        new_stage_threshold_json=json.dumps(contract["new_stage_threshold"]),
        api_endpoints_json=json.dumps(contract["api_endpoints"]),
        reject_endpoint_enabled_json=json.dumps(contract["reject_endpoint_enabled"]),
    ).strip()
    return f"{system_prompt}\n\n{user_prompt}"


def render_app_gitops_prompt(
    contract: dict[str, object],
    spec: dict,
    app_path: Path,
    gitops_path: Path,
    current_files: dict[str, str],
) -> str:
    system_prompt = (
        PROMPTS_DIR / "app_gitops_codegen_system.txt"
    ).read_text(encoding="utf-8").strip()
    user_template = (
        PROMPTS_DIR / "app_gitops_codegen_user_template.txt"
    ).read_text(encoding="utf-8")
    k8s = spec["deployment"]["k8s"]
    deployment = k8s["deployment"]
    service = k8s["service"]
    app_dir_name = app_path.name
    user_prompt = user_template.format(
        app_path=str(app_path),
        gitops_path=str(gitops_path),
        schema_version_json=json.dumps(contract["schema_version"]),
        change_id_json=json.dumps(contract["change_id"]),
        service_json=json.dumps(contract["service"]),
        baseline_stages_json=json.dumps(contract["baseline_stage_names"]),
        new_stage_name_json=json.dumps(contract["new_stage_name"]),
        new_stage_threshold_json=json.dumps(contract["new_stage_threshold"]),
        api_endpoints_json=json.dumps(contract["api_endpoints"]),
        reject_endpoint_enabled_json=json.dumps(contract["reject_endpoint_enabled"]),
        deployment_environment_json=json.dumps(spec["deployment"]["environment"]),
        k8s_namespace_json=json.dumps(k8s["namespace"]),
        k8s_deployment_name_json=json.dumps(deployment["name"]),
        k8s_replicas_json=json.dumps(deployment["replicas"]),
        k8s_container_port_json=json.dumps(deployment["container_port"]),
        k8s_service_name_json=json.dumps(service["name"]),
        k8s_service_port_json=json.dumps(service["port"]),
        k8s_service_target_port_json=json.dumps(service["target_port"]),
        k8s_ingress_enabled_json=json.dumps(k8s.get("ingress", {}).get("enabled", False)),
        current_app_main_py_json=json.dumps(current_files["app_main_py"]),
        current_k8s_namespace_yaml_json=json.dumps(current_files["k8s_namespace_yaml"]),
        current_k8s_deployment_yaml_json=json.dumps(current_files["k8s_deployment_yaml"]),
        current_k8s_service_yaml_json=json.dumps(current_files["k8s_service_yaml"]),
        current_k8s_ingress_yaml_json=json.dumps(current_files["k8s_ingress_yaml"]),
        image_repository_placeholder=app_dir_name,
        ingress_host=ingress_host_for_app(app_dir_name),
    ).strip()
    return f"{system_prompt}\n\n{user_prompt}"


def extract_constants(module_source: str) -> dict[str, object]:
    tree = ast.parse(module_source)
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


def ollama_generate_text(prompt: str, model: str, base_url: str, timeout_seconds: int) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }

    req = request.Request(
        url=f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(f"Ollama request failed: {exc}") from exc

    response_text = body.get("response", "").strip()
    if not response_text:
        raise SystemExit("Ollama returned empty code response")
    return response_text


def llm_contract_codegen_with_ollama(
    contract: dict[str, object],
    model: str,
    base_url: str,
    timeout_seconds: int,
) -> str:
    response_text = ollama_generate_text(
        render_contract_prompt(contract),
        model,
        base_url,
        timeout_seconds,
    )

    try:
        parsed = extract_constants(response_text)
    except SyntaxError as exc:
        raise SystemExit(f"Ollama returned invalid Python: {exc}") from exc

    expected = {
        "SCHEMA_VERSION": contract["schema_version"],
        "CHANGE_ID": contract["change_id"],
        "SERVICE": contract["service"],
        "BASELINE_STAGES": contract["baseline_stage_names"],
        "NEW_STAGE_NAME": contract["new_stage_name"],
        "NEW_STAGE_THRESHOLD": contract["new_stage_threshold"],
    }
    for key, value in expected.items():
        if parsed.get(key) != value:
            raise SystemExit(f"Ollama output mismatch for {key}")

    return response_text if response_text.endswith("\n") else response_text + "\n"


def llm_app_gitops_bundle_with_ollama(
    contract: dict[str, object],
    spec: dict,
    app_path: Path,
    gitops_path: Path,
    current_files: dict[str, str],
    model: str,
    base_url: str,
    timeout_seconds: int,
) -> dict[str, str]:
    response_text = ollama_generate_text(
        render_app_gitops_prompt(contract, spec, app_path, gitops_path, current_files),
        model,
        base_url,
        timeout_seconds,
    )
    bundle = parse_json_object(response_text)

    expected_keys = {
        "app_main_py",
        "k8s_namespace_yaml",
        "k8s_deployment_yaml",
        "k8s_service_yaml",
        "k8s_ingress_yaml",
    }
    if set(bundle) != expected_keys:
        raise SystemExit(
            f"Ollama bundle keys mismatch: expected {sorted(expected_keys)}, got {sorted(bundle)}"
        )

    return bundle


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = load_resolved_spec(spec_path)
    service = spec["service"]
    workspace = spec.get("workspace", {})
    app_path_str = workspace.get("path", str(spec_path.resolve().parents[1]))
    manifest_path_str = workspace.get("manifest_path", f"devops/k8s/{Path(app_path_str).name}")
    app_root = Path(app_path_str).resolve()
    app_dir_name = app_root.name
    source_root = app_root / "src"
    if not app_root.is_dir():
        raise SystemExit(f"Could not resolve application root for spec: {spec_path}")
    gitops_root = Path(manifest_path_str).resolve()
    generated_dir = source_root / "generated"
    contract_path = generated_dir / "spec_contract.py"
    init_path = generated_dir / "__init__.py"
    source_init_path = source_root / "__init__.py"
    app_main_path = source_root / "main.py"
    app_readme_path = app_root / "README.md"
    src_readme_path = source_root / "README.md"
    tests_root = app_root / "tests"
    tests_readme_path = tests_root / "README.md"
    tests_module_path = tests_root / "test_generated_placeholder.py"
    dockerfile_path = app_root / "Dockerfile"
    namespace_path = gitops_root / "namespace.yaml"
    deployment_path = gitops_root / "deployment.yaml"
    service_path = gitops_root / "service.yaml"
    ingress_path = gitops_root / "ingress.yaml"
    argocd_root = Path("devops/k8s/argocd").resolve()
    argocd_config = argocd_config_from_spec(spec, app_dir_name)
    argocd_application_path = argocd_root / f"{app_dir_name}-application.yaml"

    contract = expected_contract(spec)
    current_files = {
        "app_main_py": app_main_path.read_text(encoding="utf-8")
        if app_main_path.exists()
        else "",
        "k8s_namespace_yaml": namespace_path.read_text(encoding="utf-8")
        if namespace_path.exists()
        else "",
        "k8s_deployment_yaml": deployment_path.read_text(encoding="utf-8")
        if deployment_path.exists()
        else "",
        "k8s_service_yaml": service_path.read_text(encoding="utf-8")
        if service_path.exists()
        else "",
        "k8s_ingress_yaml": ingress_path.read_text(encoding="utf-8")
        if ingress_path.exists()
        else "",
    }

    if args.provider == "ollama":
        contract_source = llm_contract_codegen_with_ollama(
            contract, args.ollama_model, args.ollama_base_url, args.ollama_timeout_seconds
        )
        bundle = llm_app_gitops_bundle_with_ollama(
            contract,
            spec,
            app_root,
            gitops_root,
            current_files,
            args.ollama_model,
            args.ollama_base_url,
            args.ollama_timeout_seconds,
        )
        app_source = bundle["app_main_py"]
        namespace_source = bundle["k8s_namespace_yaml"]
        deployment_source = bundle["k8s_deployment_yaml"]
        service_source = bundle["k8s_service_yaml"]
        ingress_source = bundle["k8s_ingress_yaml"]
        app_violations = validate_app_source_against_spec(app_source, spec)
        if app_violations:
            app_source = app_module_body_from_contract(contract)
            namespace_source = namespace_manifest_from_spec(spec)
            deployment_source = deployment_manifest_from_spec(spec, app_dir_name)
            service_source = service_manifest_from_spec(spec)
            ingress_source = ingress_manifest_from_spec(spec, app_dir_name)
            app_codegen_provider = "ollama-validated-fallback"
        else:
            app_codegen_provider = "ollama"
    else:
        contract_source = module_body_from_contract(contract)
        if service == "expense-workflow":
            app_source = app_module_body_from_contract(contract)
        else:
            app_source = generic_app_module_body(contract, service.replace("-", " ").title())
        namespace_source = namespace_manifest_from_spec(spec)
        deployment_source = deployment_manifest_from_spec(spec, app_dir_name)
        service_source = service_manifest_from_spec(spec)
        ingress_source = ingress_manifest_from_spec(spec, app_dir_name)
        app_codegen_provider = "deterministic-template"
    argocd_application_source = ""
    if argocd_config["enabled"]:
        argocd_application_source = argocd_application_manifest_from_spec(
            spec,
            app_dir_name,
            manifest_path_str,
        )

    generated_dir.mkdir(parents=True, exist_ok=True)
    tests_root.mkdir(parents=True, exist_ok=True)
    gitops_root.mkdir(parents=True, exist_ok=True)
    argocd_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    source_init_path.write_text("", encoding="utf-8")
    init_path.write_text("", encoding="utf-8")
    contract_path.write_text(contract_source, encoding="utf-8")
    app_main_path.write_text(app_source, encoding="utf-8")
    dockerfile_path.write_text(dockerfile_body(app_dir_name), encoding="utf-8")
    app_readme_path.write_text(service_readme_body(app_dir_name), encoding="utf-8")
    src_readme_path.write_text(src_readme_body(), encoding="utf-8")
    tests_readme_path.write_text(tests_readme_body(), encoding="utf-8")
    tests_module_path.write_text(tests_module_body(app_dir_name), encoding="utf-8")
    namespace_path.write_text(namespace_source, encoding="utf-8")
    deployment_path.write_text(deployment_source, encoding="utf-8")
    service_path.write_text(service_source, encoding="utf-8")
    ingress_path.write_text(ingress_source, encoding="utf-8")
    if argocd_config["enabled"]:
        argocd_application_path.write_text(argocd_application_source, encoding="utf-8")

    release_id = spec["change_id"]
    evidence_dir = Path(args.output_root) / release_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "release_id": release_id,
        "service": service,
        "module_path": str(contract_path),
        "app_module_path": str(app_main_path),
        "provider": args.provider,
        "app_codegen_provider": app_codegen_provider,
        "gitops_codegen_provider": app_codegen_provider,
        "argocd_codegen_provider": "deterministic-template" if argocd_config["enabled"] else None,
        "ollama_model": args.ollama_model if args.provider == "ollama" else None,
        "app_path": str(app_root),
        "gitops_path": str(gitops_root),
        "argocd_application_path": str(argocd_application_path) if argocd_config["enabled"] else None,
        "constants": contract,
        "app_routes": [
            {"method": method, "path": path}
            for method, path in sorted(route_map_from_source(app_source))
        ],
        "manifest_summary": summarize_manifests(
            namespace_source,
            deployment_source,
            service_source,
            ingress_source,
        ),
        "argocd_application": summarize_argocd_application(argocd_application_source),
        "generated_files": [
            str(contract_path.resolve()),
            str(source_init_path.resolve()),
            str(app_main_path.resolve()),
            str(dockerfile_path.resolve()),
            str(app_readme_path.resolve()),
            str(src_readme_path.resolve()),
            str(tests_readme_path.resolve()),
            str(tests_module_path.resolve()),
            str(namespace_path.resolve()),
            str(deployment_path.resolve()),
            str(service_path.resolve()),
            str(ingress_path.resolve()),
            *(
                [str(argocd_application_path.resolve())]
                if argocd_config["enabled"]
                else []
            ),
        ],
    }
    (evidence_dir / "codegen-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Generated code artifact: {contract_path}")
    print(f"Generated app source: {app_main_path}")
    print(f"Generated GitOps manifests under: {gitops_root}")
    if argocd_config["enabled"]:
        print(f"Generated Argo CD application: {argocd_application_path}")
    print(f"Codegen provider: {args.provider}")


if __name__ == "__main__":
    main()
