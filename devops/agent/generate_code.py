#!/usr/bin/env python
"""Generate application code artifacts from spec (deterministic or ollama-backed)."""

import argparse
import ast
import json
from pathlib import Path
from urllib import error, request

import yaml

SERVICE_SOURCE_ROOTS = {
    "expense-workflow": Path("applications/expense-workflow-service/src"),
}
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
        f'SCHEMA_VERSION = {json.dumps(contract["schema_version"])}',
        f'CHANGE_ID = {json.dumps(contract["change_id"])}',
        f'SERVICE = {json.dumps(contract["service"])}',
        f'BASELINE_STAGES = {json.dumps(contract["baseline_stage_names"])}',
    ]

    if contract["new_stage_name"] is not None:
        lines.append(f'NEW_STAGE_NAME = {json.dumps(contract["new_stage_name"])}')
        lines.append(f'NEW_STAGE_THRESHOLD = {json.dumps(contract["new_stage_threshold"])}')
    else:
        lines.append("NEW_STAGE_NAME = None")
        lines.append("NEW_STAGE_THRESHOLD = None")

    lines.append(f'API_ENDPOINTS = {json.dumps(contract["api_endpoints"])}')
    lines.append(f'REJECT_ENDPOINT_ENABLED = {json.dumps(contract["reject_endpoint_enabled"])}')
    lines.append("")
    return "\n".join(lines)


def app_module_body_from_contract(contract: dict[str, object]) -> str:
    reject_enabled = "True" if contract["reject_endpoint_enabled"] else "False"
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


@app.post("/expenses/{{expense_id}}/reject")
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
        {{
            "expense_id": expense_id,
            "rejected_by": req.role,
            "reason_code": req.reason_code,
        }},
    )

    return expense


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


setup_tracing()
'''


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


def render_prompt(contract: dict[str, object]) -> str:
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


def llm_codegen_with_ollama(
    contract: dict[str, object],
    model: str,
    base_url: str,
) -> str:
    prompt = render_prompt(contract)

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
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(f"Ollama request failed: {exc}") from exc

    response_text = body.get("response", "").strip()
    if not response_text:
        raise SystemExit("Ollama returned empty code response")

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


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    service = spec["service"]
    if service not in SERVICE_SOURCE_ROOTS:
        raise SystemExit(f"Unsupported service for code generation: {service}")

    source_root = SERVICE_SOURCE_ROOTS[service]
    generated_dir = source_root / "generated"
    contract_path = generated_dir / "spec_contract.py"
    init_path = generated_dir / "__init__.py"
    app_main_path = source_root / "main.py"

    contract = expected_contract(spec)

    if args.provider == "ollama":
        contract_source = llm_codegen_with_ollama(contract, args.ollama_model, args.ollama_base_url)
        app_source = app_module_body_from_contract(contract)
        app_codegen_provider = "deterministic-template"
    else:
        contract_source = module_body_from_contract(contract)
        app_source = app_module_body_from_contract(contract)
        app_codegen_provider = "deterministic-template"

    generated_dir.mkdir(parents=True, exist_ok=True)
    init_path.write_text("", encoding="utf-8")
    contract_path.write_text(contract_source, encoding="utf-8")
    app_main_path.write_text(app_source, encoding="utf-8")

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
        "ollama_model": args.ollama_model if args.provider == "ollama" else None,
        "constants": contract,
        "generated_files": [
            str(contract_path),
            str(app_main_path),
        ],
    }
    (evidence_dir / "codegen-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Generated code artifact: {contract_path}")
    print(f"Generated app source: {app_main_path}")
    print(f"Codegen provider: {args.provider}")


if __name__ == "__main__":
    main()
