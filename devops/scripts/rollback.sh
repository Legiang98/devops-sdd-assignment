#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <RELEASE_ID>"
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_ID="$1"
TARGET="$ROOT/build/releases/${RELEASE_ID}"
RUNTIME_DIR="$ROOT/deploy"

if [ ! -d "$TARGET" ]; then
  echo "Rollback target not found: $TARGET"
  exit 1
fi

mkdir -p "$RUNTIME_DIR"
ln -sfn "$TARGET" "$RUNTIME_DIR/current"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback ${RELEASE_ID}" >> "$RUNTIME_DIR/history.log"

echo "Rollback pointer moved to ${RELEASE_ID}"
