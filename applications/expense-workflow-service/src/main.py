import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from fastapi.responses import Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

RULES_PATH = os.getenv("RULES_PATH", "deploy/current/rules.json")
RELEASE_ID_FILE = os.getenv("RELEASE_ID_FILE", "deploy/current/release_id.txt")

app = FastAPI(title="Expense Workflow Service")

expense_submitted_total = Counter("expense_submitted_total", "Submitted expenses")
approval_step_required_total = Counter(
    "approval_step_required_total", "Required approvals by step", ["step"]
)
approval_step_completed_total = Counter(
    "approval_step_completed_total", "Completed approvals by step", ["step"]
)
expense_approved_total = Counter("expense_approved_total", "Fully approved expenses")

EXPENSES: dict[str, dict[str, Any]] = {}


def setup_tracing() -> None:
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        return

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4318",
    ).rstrip("/")
    service_name = os.getenv("OTEL_SERVICE_NAME", "expense-workflow-service")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


class SubmitExpenseRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str


class ApproveExpenseRequest(BaseModel):
    role: str


def read_release_id() -> str:
    try:
        with open(RELEASE_ID_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "UNKNOWN"


def load_rules() -> dict[str, Any]:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def required_stages_for_amount(amount: float, rules: dict[str, Any]) -> list[str]:
    stages = []
    for stage in rules["workflow"]["stages"]:
        threshold = float(stage["required_when"]["amount_gte"])
        if amount >= threshold:
            stages.append(stage["name"])
    return stages


def audit(event: str, payload: dict[str, Any]) -> None:
    log_line = {
        "ts": int(time.time()),
        "release_id": read_release_id(),
        "event": event,
        "payload": payload,
    }
    print(json.dumps(log_line), flush=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "release_id": read_release_id()}


@app.post("/expenses")
def submit_expense(req: SubmitExpenseRequest) -> dict[str, Any]:
    rules = load_rules()
    stages = required_stages_for_amount(req.amount, rules)

    expense_id = str(uuid.uuid4())
    EXPENSES[expense_id] = {
        "id": expense_id,
        "amount": req.amount,
        "description": req.description,
        "required_stages": stages,
        "approved_stages": [],
        "status": "PENDING_APPROVAL",
    }

    expense_submitted_total.inc()
    for step in stages:
        approval_step_required_total.labels(step=step).inc()

    audit(
        "expense_submitted",
        {
            "expense_id": expense_id,
            "amount": req.amount,
            "required_stages": stages,
        },
    )

    return EXPENSES[expense_id]


@app.post("/expenses/{expense_id}/approve")
def approve_expense(expense_id: str, req: ApproveExpenseRequest) -> dict[str, Any]:
    expense = EXPENSES.get(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if req.role not in expense["required_stages"]:
        raise HTTPException(status_code=400, detail=f"Role {req.role} is not required")

    if req.role in expense["approved_stages"]:
        return expense

    expense["approved_stages"].append(req.role)
    approval_step_completed_total.labels(step=req.role).inc()

    if set(expense["approved_stages"]) == set(expense["required_stages"]):
        expense["status"] = "APPROVED"
        expense_approved_total.inc()

    audit(
        "expense_approved_step",
        {
            "expense_id": expense_id,
            "approved_role": req.role,
            "status": expense["status"],
        },
    )

    return expense


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


setup_tracing()
