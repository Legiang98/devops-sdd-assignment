#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="${1:-applications/expense-workflow-service/specs/CHG-001-expense-finance-approval.yaml}"

echo "[generate] spec=$SPEC"
python devops/agent/generate.py --spec "$SPEC"
