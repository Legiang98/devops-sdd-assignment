#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="${1:-applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml}"
REPORT_DIR="${2:-build/policy}"

echo "[gate] spec=$SPEC"
echo "[gate] report_dir=$REPORT_DIR"
echo "[gate] policy scan 1/2: validate spec"
python3 devops/policy/validate_spec.py --spec "$SPEC" --report-dir "$REPORT_DIR"
if command -v opa >/dev/null 2>&1; then
  echo "[gate] opa detected, running simple generated-output policy"
  POLICY_INPUT="$(mktemp)"
  trap 'rm -f "$POLICY_INPUT"' EXIT

  python3 - "$SPEC" "$POLICY_INPUT" <<'PY'
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from devops.spec.specs import load_resolved_spec


def extract_constants(module_path: Path) -> dict[str, object]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    result: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(node.value, ast.Constant):
            result[target.id] = node.value.value
        elif isinstance(node.value, ast.List):
            values = []
            for item in node.value.elts:
                if isinstance(item, ast.Constant):
                    values.append(item.value)
            result[target.id] = values
    return result


def route_map(module_path: Path) -> list[dict[str, str]]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    routes: list[dict[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "app":
                continue
            if not decorator.args:
                continue
            first_arg = decorator.args[0]
            if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
                continue
            routes.append({"method": func.attr.upper(), "path": first_arg.value})
    return routes


spec_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
spec = load_resolved_spec(spec_path)
workspace = spec.get("workspace", {})
app_root = Path(workspace.get("path", spec_path.resolve().parents[1])).resolve()
source_root = app_root / workspace.get("src_path", "src")
contract_path = source_root / "generated" / "spec_contract.py"
app_main_path = source_root / "main.py"
constants = extract_constants(contract_path)

payload = {
    "spec": spec,
    "generated": {
        "contract": {
            "schema_version": constants.get("SCHEMA_VERSION"),
            "change_id": constants.get("CHANGE_ID"),
            "service": constants.get("SERVICE"),
            "baseline_stages": constants.get("BASELINE_STAGES"),
            "new_stage_name": constants.get("NEW_STAGE_NAME"),
            "new_stage_threshold": constants.get("NEW_STAGE_THRESHOLD"),
        },
        "app_routes": route_map(app_main_path),
    },
}
output_path.write_text(json.dumps(payload), encoding="utf-8")
PY

  if ! opa eval --fail-defined -d devops/policy/generated_output.rego -i "$POLICY_INPUT" \
    'data.policy.generated_output.deny[_]' >/dev/null; then
    echo "[gate] simple OPA policy failed"
    opa eval --format=pretty -d devops/policy/generated_output.rego -i "$POLICY_INPUT" \
      'data.policy.generated_output.deny'
    exit 1
  fi

  echo "[gate] simple OPA policy passed"
else
  echo "[gate] opa not found, skipping simple OPA policy"
fi
echo "[gate] policy scan 2/2: validate generated application output"
python3 devops/policy/validate_generated_output.py --spec "$SPEC" --report-dir "$REPORT_DIR"
echo "[gate] all policy scans passed"
