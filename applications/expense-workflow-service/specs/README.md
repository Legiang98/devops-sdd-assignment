# Service Specs

Versioned change specs reviewed in Git.
These specs are consumed by `devops/agent/run_agent.py`.

Minimal field intent:
- `schema_version`: version of the spec format (semantic version, e.g. `1.0.0`)
- `change_id`: identifier of the business change request (e.g. `EXP-FINANCE-APPROVAL`)
- `deployment.k8s`: declarative runtime deployment intent for GitOps (namespace, deployment, service; ingress optional for local demo)

Naming convention (recommended):
- `EXP-<id>-<feature>.yaml` for change specs (example: `EXP-finance-approval.yaml`)
