# Service Specs

Versioned change specs reviewed in Git.
These specs are consumed by `devops/agent/run_agent.py`.

Minimal field intent:
- `schema_version`: version of the spec format (semantic version, e.g. `1.0.0`)
- `change_id`: identifier of the business change request (e.g. `CHG-001`)

Naming convention (recommended):
- `EXP-<id>-<feature>.yaml` for change specs (example: `EXP-001-expense-finance-approval.yaml`)
