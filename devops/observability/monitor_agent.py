#!/usr/bin/env python3
"""PoC post-deployment monitoring agent.

Reads collected evidence, applies simple heuristics, and writes a recommendation.
The agent is read-only and never performs rollback.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze post-deployment evidence")
    parser.add_argument("--evidence-dir", required=True, help="Directory containing evidence files")
    parser.add_argument("--service", required=True, help="Service name for reporting")
    return parser.parse_args()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(health: dict, loki: dict, context: dict, service: str) -> dict:
    findings: list[str] = []
    severity = "info"
    recommendation = "observe"

    health_code = health.get("http_status")
    if health_code != 200:
        findings.append(f"Health check returned {health_code!r} for {service}.")
        severity = "high"
        recommendation = "rollback"

    results = ((loki.get("data") or {}).get("result") or []) if isinstance(loki, dict) else []
    log_line_count = sum(
        len(stream.get("values") or [])
        for stream in results
        if isinstance(stream, dict)
    )
    findings.append(f"Loki returned {len(results)} streams and {log_line_count} log lines.")

    if not results:
        findings.append("No Loki log streams found for the deployment window.")
        if recommendation != "rollback":
            severity = "medium"
            recommendation = "observe"

    change_id = context.get("change_id", "unknown")
    current_version = context.get("current_version", "unknown")
    previous_healthy_version = context.get("previous_healthy_version", "unknown")

    if recommendation == "rollback":
        reason = (
            f"Deployment {change_id} for {service} looks unhealthy. "
            f"Current version {current_version} should be compared against previous healthy version {previous_healthy_version}."
        )
    else:
        reason = (
            f"Deployment {change_id} for {service} has no strong rollback signal from the current evidence set."
        )

    return {
        "service": service,
        "change_id": change_id,
        "severity": severity,
        "recommendation": recommendation,
        "reason": reason,
        "analysis": "\n".join(f"- {item}" for item in findings),
        "findings": findings,
    }


def main() -> None:
    args = parse_args()
    evidence_dir = Path(args.evidence_dir)

    health = read_json(evidence_dir / "health_status.json")
    loki = read_json(evidence_dir / "loki_response.json")
    context = read_json(evidence_dir / "deployment_context.json")

    result = analyze(health, loki, context, args.service)
    output_path = evidence_dir / "analysis_result.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
