#!/usr/bin/env python
"""Generate application code artifacts from spec (deterministic or ollama-backed)."""

import argparse
import ast
import json
from pathlib import Path
from urllib import error, request

import yaml

SERVICE_SOURCE_ROOTS = {
    "expense-workflow": Path("applications/expense-workflow-service/src"),
}
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate code artifacts from a change spec")
    parser.add_argument("--spec", required=True, help="Path to YAML spec")
    parser.add_argument("--output-root", default="build/releases", help="Release root")
    parser.add_argument(
        "--provider",
        choices=["deterministic", "ollama"],
        default="deterministic",
        help="Code generation backend",
    )
    parser.add_argument(
        "--ollama-model",
        default="qwen2.5:7b",
        help="Ollama model name",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
        help="Ollama base URL",
    )
    return parser.parse_args()


def expected_contract(spec: dict) -> dict[str, object]:
    baseline_stages = spec["workflow_change"]["baseline_stages"]
    baseline_stage_names = [stage["name"] for stage in baseline_stages]
    new_stage = spec["workflow_change"].get("new_stage")

    return {
        "schema_version": spec["schema_version"],
        "change_id": spec["change_id"],
        "service": spec["service"],
        "baseline_stage_names": baseline_stage_names,
        "new_stage_name": new_stage["name"] if new_stage else None,
        "new_stage_threshold": (
            new_stage["required_when"]["amount_gte"] if new_stage else None
        ),
    }


def module_body_from_contract(contract: dict[str, object]) -> str:
    lines = [
        '"""Auto-generated from spec. Do not edit manually."""',
        "",
        f'SCHEMA_VERSION = {json.dumps(contract["schema_version"])}',
        f'CHANGE_ID = {json.dumps(contract["change_id"])}',
        f'SERVICE = {json.dumps(contract["service"])}',
        f'BASELINE_STAGES = {json.dumps(contract["baseline_stage_names"])}',
    ]

    if contract["new_stage_name"] is not None:
        lines.append(f'NEW_STAGE_NAME = {json.dumps(contract["new_stage_name"])}')
        lines.append(f'NEW_STAGE_THRESHOLD = {json.dumps(contract["new_stage_threshold"])}')
    else:
        lines.append("NEW_STAGE_NAME = None")
        lines.append("NEW_STAGE_THRESHOLD = None")

    lines.append("")
    return "\n".join(lines)


def extract_constants(module_source: str) -> dict[str, object]:
    tree = ast.parse(module_source)
    constants: dict[str, object] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        if isinstance(node.value, ast.Constant):
            constants[target.id] = node.value.value
        elif isinstance(node.value, ast.List):
            values: list[object] = []
            for item in node.value.elts:
                if isinstance(item, ast.Constant):
                    values.append(item.value)
            constants[target.id] = values

    return constants


def render_prompt(contract: dict[str, object]) -> str:
    system_prompt = (PROMPTS_DIR / "codegen_system.txt").read_text(encoding="utf-8").strip()
    user_template = (PROMPTS_DIR / "codegen_user_template.txt").read_text(encoding="utf-8")
    user_prompt = user_template.format(
        schema_version_json=json.dumps(contract["schema_version"]),
        change_id_json=json.dumps(contract["change_id"]),
        service_json=json.dumps(contract["service"]),
        baseline_stages_json=json.dumps(contract["baseline_stage_names"]),
        new_stage_name_json=json.dumps(contract["new_stage_name"]),
        new_stage_threshold_json=json.dumps(contract["new_stage_threshold"]),
    ).strip()
    return f"{system_prompt}\n\n{user_prompt}"


def llm_codegen_with_ollama(
    contract: dict[str, object],
    model: str,
    base_url: str,
) -> str:
    prompt = render_prompt(contract)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }

    req = request.Request(
        url=f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(f"Ollama request failed: {exc}") from exc

    response_text = body.get("response", "").strip()
    if not response_text:
        raise SystemExit("Ollama returned empty code response")

    try:
        parsed = extract_constants(response_text)
    except SyntaxError as exc:
        raise SystemExit(f"Ollama returned invalid Python: {exc}") from exc

    expected = {
        "SCHEMA_VERSION": contract["schema_version"],
        "CHANGE_ID": contract["change_id"],
        "SERVICE": contract["service"],
        "BASELINE_STAGES": contract["baseline_stage_names"],
        "NEW_STAGE_NAME": contract["new_stage_name"],
        "NEW_STAGE_THRESHOLD": contract["new_stage_threshold"],
    }
    for key, value in expected.items():
        if parsed.get(key) != value:
            raise SystemExit(f"Ollama output mismatch for {key}")

    return response_text if response_text.endswith("\n") else response_text + "\n"


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    service = spec["service"]
    if service not in SERVICE_SOURCE_ROOTS:
        raise SystemExit(f"Unsupported service for code generation: {service}")

    source_root = SERVICE_SOURCE_ROOTS[service]
    generated_dir = source_root / "generated"
    module_path = generated_dir / "spec_contract.py"
    init_path = generated_dir / "__init__.py"

    contract = expected_contract(spec)

    if args.provider == "ollama":
        module_source = llm_codegen_with_ollama(contract, args.ollama_model, args.ollama_base_url)
    else:
        module_source = module_body_from_contract(contract)

    generated_dir.mkdir(parents=True, exist_ok=True)
    init_path.write_text("", encoding="utf-8")
    module_path.write_text(module_source, encoding="utf-8")

    release_id = spec["change_id"]
    evidence_dir = Path(args.output_root) / release_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "release_id": release_id,
        "service": service,
        "module_path": str(module_path),
        "provider": args.provider,
        "ollama_model": args.ollama_model if args.provider == "ollama" else None,
        "constants": contract,
    }
    (evidence_dir / "codegen-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Generated code artifact: {module_path}")
    print(f"Codegen provider: {args.provider}")


if __name__ == "__main__":
    main()
