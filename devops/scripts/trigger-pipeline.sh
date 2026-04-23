#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mkdir -p logs
LOG_FILE="logs/pipeline.log"

main() {
  SPEC="${1:-applications/expense-workflow-service/specs/CHG-001-expense-finance-approval.yaml}"
  RELEASE_ID="${2:-CHG-001}"
  RELEASE_DIR="build/releases/${RELEASE_ID}"

  echo "[trigger-pipeline] start"
  echo "[trigger-pipeline] step 1/2: agent generation"
  python devops/agent/generate.py --spec "$SPEC"

  echo "[trigger-pipeline] step 2/2: policy gate"
  python devops/policy/check_spec_alignment.py --spec "$SPEC" --release-dir "$RELEASE_DIR"

  echo "[trigger-pipeline] pipeline passed"
}

main "$@" 2>&1 | tee -a "$LOG_FILE"
