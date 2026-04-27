"""Auto-generated service module from spec. Do not edit manually."""

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
REJECT_ENDPOINT_ENABLED = False

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

EXPENSES: dict[str, dict[str, Any]] = {}


def setup_tracing() -> None:
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        return

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4318",
    ).rstrip("/")
    service_name = os.getenv("OTEL_SERVICE_NAME", SERVICE)

    resource = Resource.create(
        {
            "service.name": service_name,
            "spec.schema_version": SCHEMA_VERSION,
            "spec.change_id": CHANGE_ID,
        }
    )
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
        stages = [{"name": s, "required_when": {"amount_gte": 0}} for s in BASELINE_STAGES]
        if NEW_STAGE_NAME is not None:
            stages.append(
                {
                    "name": NEW_STAGE_NAME,
                    "required_when": {
                        "amount_gte": 0 if NEW_STAGE_THRESHOLD is None else NEW_STAGE_THRESHOLD
                    },
                }
            )
        return {"workflow": {"stages": stages}}


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
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "event": event,
        "payload": payload,
    }
    print(json.dumps(log_line), flush=True)


@app.get("/health")
@app.get("/healthz")
@app.get("/readiness")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "release_id": read_release_id(),
        "change_id": CHANGE_ID,
        "service": SERVICE,
    }


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

    if expense["status"] == "REJECTED":
        raise HTTPException(status_code=400, detail="Expense already rejected")

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







@app.get("/expenses/{expense_id}/status")
def get_expense_status(expense_id: str) -> dict[str, Any]:
    expense = EXPENSES.get(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return {
        "id": expense["id"],
        "status": expense["status"],
        "required_stages": expense["required_stages"],
        "approved_stages": expense["approved_stages"],
    }






@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


setup_tracing()
