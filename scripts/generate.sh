#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="${1:-applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml}"
CODEGEN_PROVIDER="${2:-deterministic}"
OLLAMA_MODEL="${3:-qwen2.5:7b}"
OLLAMA_BASE_URL="${4:-http://127.0.0.1:11434}"

echo "[generate] spec=$SPEC"
echo "[generate] codegen_provider=$CODEGEN_PROVIDER"
python3 devops/agent/generate.py \
  --spec "$SPEC" \
  --codegen-provider "$CODEGEN_PROVIDER" \
  --ollama-model "$OLLAMA_MODEL" \
  --ollama-base-url "$OLLAMA_BASE_URL"
