# Service Specs

Versioned change specs reviewed in Git.
These specs are consumed by `devops/agent/run_agent.py`.

Spec model:
- `BASELINE.yaml` is the full service baseline.
- Feature specs are merged over `BASELINE.yaml` before generation and policy checks.
- Each feature spec should describe one small business change, not a full snapshot of the service.
- `api_contract.endpoints` in a feature spec are treated as feature-relevant endpoints and merged with baseline endpoints.

Minimal field intent:
- `schema_version`: version of the spec format (semantic version, e.g. `1.0.0`)
- `change_id`: identifier of the business change request (e.g. `EXP-FINANCE-APPROVAL`)
- `deployment.k8s`: declarative runtime deployment intent for GitOps (namespace, deployment, service; ingress optional for local demo)
- `docs.swagger`: required API documentation declaration (`path` or `url`)

Naming convention (recommended):
- `EXP-<id>-<feature>.yaml` for change specs (example: `EXP-finance-approval.yaml`)
