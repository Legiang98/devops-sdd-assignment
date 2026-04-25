.PHONY: install generate gate pipeline demo serve verify rollback

SPEC       ?= applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml
RELEASE_ID ?= EXP-FINANCE-APPROVAL
CODEGEN    ?= deterministic
APP_URL    ?= http://localhost:8000

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

generate:
	./scripts/generate.sh "$(SPEC)" "$(CODEGEN)"

gate:
	./scripts/gate.sh "$(SPEC)" "$(RELEASE_ID)"

pipeline: generate gate

demo:
	./scripts/demo_gate_failure.sh

serve:
	PYTHONPATH=applications/expense-workflow-service python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000

verify:
	python3 devops/observability/verify_behavior.py --base-url "$(APP_URL)"

rollback:
	./scripts/rollback.sh BASELINE
