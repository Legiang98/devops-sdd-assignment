from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, Counter

app = FastAPI()
metrics_counter = Counter("invoice_requests_total", "Total invoice requests")

@app.get("/")
def read_root():
    return {"message": "Invoice Workflow Service"}

@app.get("/health")
@app.get("/healthz")
@app.get("/readiness")
def health():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
