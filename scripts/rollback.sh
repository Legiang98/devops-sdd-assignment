#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REF="${1:-HEAD~1}"

echo "[rollback] Restoring Kubernetes manifests from git ref: $REF"
git restore --source "$REF" -- devops/k8s

echo "[rollback] Kubernetes manifests restored in working tree"
echo "[rollback] Commit/push this change if you want Argo CD to sync rollback state"
