#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="$ROOT/applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml"
RELEASE_DIR="$ROOT/build/releases/EXP-FINANCE-APPROVAL"

echo "[1/4] Generating mismatched artifacts"
python3 "$ROOT/devops/agent/run_agent.py" \
  --spec "$SPEC" \
  --output-root "$ROOT/build/releases" \
  --simulate-mismatch

echo "[2/4] Running policy gate (expected to fail)"
if python3 "$ROOT/devops/policy/validate_contract_artifacts.py" --spec "$SPEC" --release-dir "$RELEASE_DIR"; then
  echo "ERROR: policy should have failed but passed"
  exit 1
fi

echo "[3/4] Regenerating corrected artifacts"
python3 "$ROOT/devops/agent/run_agent.py" --spec "$SPEC" --output-root "$ROOT/build/releases"

echo "[4/4] Running policy gate (expected to pass)"
python3 "$ROOT/devops/policy/validate_contract_artifacts.py" --spec "$SPEC" --release-dir "$RELEASE_DIR"

echo "Demo completed: gate caught mismatch, then release passed after regeneration"
