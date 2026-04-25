#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="${1:-applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml}"
RELEASE_ID="${2:-EXP-FINANCE-APPROVAL}"
RELEASE_DIR="build/releases/${RELEASE_ID}"

echo "[gate] spec=$SPEC"
echo "[gate] release_dir=$RELEASE_DIR"

if command -v opa >/dev/null 2>&1; then
  echo "[gate] opa detected, running Rego policy checks"
  POLICY_INPUT="$(mktemp)"
  trap 'rm -f "$POLICY_INPUT"' EXIT

  python3 - "$SPEC" "$RELEASE_DIR" "$POLICY_INPUT" <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from devops.spec.specs import load_resolved_spec

spec_path = Path(sys.argv[1])
release_dir = Path(sys.argv[2])
output_path = Path(sys.argv[3])

payload = {
    "spec": load_resolved_spec(spec_path),
    "generated": {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in {
            "rules": release_dir / "rules.json",
            "deploy_manifest": release_dir / "deploy_manifest.json",
            "codegen_report": release_dir / "evidence" / "codegen-report.json",
        }.items()
    },
}
output_path.write_text(json.dumps(payload), encoding="utf-8")
PY

  if ! opa eval --fail-defined -d devops/policy/spec_validation.rego -i "$POLICY_INPUT" \
    'data.policy.spec_validation.deny[_]' >/dev/null; then
    echo "[gate] spec validation failed"
    opa eval --format=pretty -d devops/policy/spec_validation.rego -i "$POLICY_INPUT" \
      'data.policy.spec_validation.deny'
    exit 1
  fi

  if ! opa eval --fail-defined -d devops/policy/generated_output.rego -i "$POLICY_INPUT" \
    'data.policy.generated_output.deny[_]' >/dev/null; then
    echo "[gate] generated output policy failed"
    opa eval --format=pretty -d devops/policy/generated_output.rego -i "$POLICY_INPUT" \
      'data.policy.generated_output.deny'
    exit 1
  fi

  echo "[gate] opa policy checks passed"
else
  echo "[gate] opa not found, skipping Rego checks"
fi

# Keep Python gates to produce evidence reports under build/releases/<id>/evidence.
python3 devops/policy/validate_contract_artifacts.py --spec "$SPEC" --release-dir "$RELEASE_DIR"
python3 devops/policy/validate_generated_output.py --spec "$SPEC" --release-dir "$RELEASE_DIR"
