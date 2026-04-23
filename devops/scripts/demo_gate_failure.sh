#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC="$ROOT/applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml"
RELEASE_DIR="$ROOT/build/releases/EXP-FINANCE-APPROVAL"

echo "[1/4] Generating mismatched artifacts"
python "$ROOT/devops/agent/run_agent.py" --spec "$SPEC" --simulate-mismatch

echo "[2/4] Running policy gate (expected to fail)"
if python "$ROOT/devops/policy/check_spec_alignment.py" --spec "$SPEC" --release-dir "$RELEASE_DIR"; then
  echo "ERROR: policy should have failed but passed"
  exit 1
fi

echo "[3/4] Regenerating corrected artifacts"
python "$ROOT/devops/agent/run_agent.py" --spec "$SPEC"

echo "[4/4] Running policy gate (expected to pass)"
python "$ROOT/devops/policy/check_spec_alignment.py" --spec "$SPEC" --release-dir "$RELEASE_DIR"

echo "Demo completed: gate caught mismatch, then release passed after regeneration"
