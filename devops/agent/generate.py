#!/usr/bin/env python
"""Developer-friendly entrypoint for spec-driven generation."""

import argparse
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate artifacts and code from spec")
    parser.add_argument("--spec", required=True, help="Path to YAML spec")
    parser.add_argument("--output-root", default="build/releases", help="Release root")
    parser.add_argument(
        "--codegen-provider",
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
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=60,
        help="Ollama request timeout in seconds",
    )
    parser.add_argument(
        "--simulate-mismatch",
        action="store_true",
        help="Intentionally generate wrong threshold for policy-gate demo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    agent_cmd = [
        sys.executable,
        "devops/agent/run_agent.py",
        "--spec",
        args.spec,
        "--output-root",
        args.output_root,
    ]
    if args.simulate_mismatch:
        agent_cmd.append("--simulate-mismatch")

    codegen_cmd = [
        sys.executable,
        "devops/agent/generate_code.py",
        "--spec",
        args.spec,
        "--output-root",
        args.output_root,
        "--provider",
        args.codegen_provider,
        "--ollama-model",
        args.ollama_model,
        "--ollama-base-url",
        args.ollama_base_url,
        "--ollama-timeout-seconds",
        str(args.ollama_timeout_seconds),
    ]

    subprocess.run(agent_cmd, check=True)
    subprocess.run(codegen_cmd, check=True)


if __name__ == "__main__":
    main()
