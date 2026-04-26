"""Auto-generated service module from spec. Do not edit manually."""

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

app = FastAPI(title="Invoice Workflow Service")

request_total = Counter("generated_request_total", "Generated placeholder requests", ["method", "path"])


@app.get("/health")
@app.get("/healthz")
@app.get("/readiness")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "schema_version": SCHEMA_VERSION,
        "baseline_stages": BASELINE_STAGES,
        "new_stage_name": NEW_STAGE_NAME,
        "new_stage_threshold": NEW_STAGE_THRESHOLD,
        "reject_endpoint_enabled": REJECT_ENDPOINT_ENABLED,
        "api_endpoints": API_ENDPOINTS,
    }


@app.post("/invoices")
def endpoint_0(payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "method": "POST",
        "path": "/invoices",
        "payload": payload or {},
        "message": "Generated endpoint placeholder",
    }

@app.get("/invoices/{invoice_id}")
def endpoint_1_path(invoice_id: str) -> dict[str, object]:
    return {
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "method": "GET",
        "path": "/invoices/{invoice_id}",
        "message": "Generated endpoint placeholder", "path_params": {"invoice_id": invoice_id},
    }

@app.post("/invoices/{invoice_id}/approve")
def endpoint_2_path(invoice_id: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "change_id": CHANGE_ID,
        "service": SERVICE,
        "method": "POST",
        "path": "/invoices/{invoice_id}/approve",
        "payload": payload or {},
        "message": "Generated endpoint placeholder", "path_params": {"invoice_id": invoice_id},
    }


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
