#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC="$ROOT/applications/expense-workflow-service/specs/BASELINE.yaml"
RELEASE_DIR="$ROOT/build/releases/BASELINE"

python "$ROOT/devops/agent/run_agent.py" --spec "$SPEC"
python "$ROOT/devops/policy/check_spec_alignment.py" --spec "$SPEC" --release-dir "$RELEASE_DIR"
"$ROOT/devops/scripts/deploy_release.sh" BASELINE

echo "Baseline release generated and deployed"
