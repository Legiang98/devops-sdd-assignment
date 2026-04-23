#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="${1:-applications/expense-workflow-service/specs/CHG-001-expense-finance-approval.yaml}"
RELEASE_ID="${2:-CHG-001}"
RELEASE_DIR="build/releases/${RELEASE_ID}"

echo "[gate] spec=$SPEC"
echo "[gate] release_dir=$RELEASE_DIR"
python devops/policy/check_spec_alignment.py --spec "$SPEC" --release-dir "$RELEASE_DIR"
