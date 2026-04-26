from fastapi import FastAPI
app = FastAPI()
@app.get("/")
def read_root():
    return {"message": "Invoice Workflow Service"}
@app.get("/health")
def health():
    return {"status": "ok"}
