#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mkdir -p logs
LOG_FILE="logs/pipeline.log"

main() {
  SPEC="${1:-applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml}"
  RELEASE_ID="${2:-EXP-FINANCE-APPROVAL}"
  CODEGEN_PROVIDER="${3:-deterministic}"
  OLLAMA_MODEL="${4:-qwen2.5:7b}"
  OLLAMA_BASE_URL="${5:-http://127.0.0.1:11434}"
  OLLAMA_TIMEOUT_SECONDS="${6:-180}"

  echo "[trigger-pipeline] start"
  echo "[trigger-pipeline] step 1/2: agent generation"
  echo "[trigger-pipeline] codegen_provider=$CODEGEN_PROVIDER"
  python3 devops/agent/generate.py \
    --spec "$SPEC" \
    --codegen-provider "$CODEGEN_PROVIDER" \
    --ollama-model "$OLLAMA_MODEL" \
    --ollama-base-url "$OLLAMA_BASE_URL" \
    --ollama-timeout-seconds "$OLLAMA_TIMEOUT_SECONDS"

  echo "[trigger-pipeline] step 2/2: policy gate"
  ./scripts/gate.sh "$SPEC" "$RELEASE_ID"

  echo "[trigger-pipeline] pipeline passed"
}

main "$@" 2>&1 | tee -a "$LOG_FILE"
