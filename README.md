# Spec-Driven DevOps PoC (Monorepo Skeleton)

This repository demonstrates one narrow vertical slice for a spec-driven, agent-assisted DevOps flow:

`requirement -> versioned spec -> agent generation -> policy gate -> deploy -> observe -> audit -> rollback`

## Monorepo Layout

- `applications/`: business application code, tests, and versioned change specs
- `devops/`: agent, policy gate, deployment delivery, observability, and rollback mechanics

## Quick Start (Local-First)

### 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Show policy gate catching a real mismatch

```bash
./devops/scripts/demo_gate_failure.sh
```

### 3) Deploy corrected release and run service

```bash
./devops/scripts/deploy_release.sh EXP-FINANCE-APPROVAL
docker compose up --build -d
```

### 4) Verify runtime behavior from telemetry

```bash
python devops/observability/verify_behavior.py --base-url http://localhost:8000
```

### Optional: Minikube monitoring stack (OTel + Alloy + Tempo + Grafana)

```bash
./devops/scripts/setup_observability_minikube.sh
```

Guide: `devops/observability/monitoring-minikube.md`

### 5) Roll back to baseline

```bash
./devops/scripts/rollback.sh BASELINE
docker compose restart app
```

## Key Paths

- Spec input: `applications/expense-workflow-service/specs/`
- Service code: `applications/expense-workflow-service/src/`
- Agent workflow: `devops/agent/run_agent.py`
- Policy gate: `devops/policy/check_spec_alignment.py`
- Release artifacts: `build/releases/<RELEASE_ID>/`
- Deploy pointer and audit history: `deploy/current`, `deploy/history.log`
- Kubernetes manifests: `devops/k8s/<service>/` and `devops/k8s/argocd/`
- Argo CD placeholder: `devops/argocd/application.yaml`
- Observability verification: `devops/observability/verify_behavior.py`

## Notes

- Kubernetes and Argo CD parts are intentionally minimal placeholders.
- No Kustomize and no patch-based deployment structure are used.
- The focus is clarity of control boundaries and end-to-end traceability.
