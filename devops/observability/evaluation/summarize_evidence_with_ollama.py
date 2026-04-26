#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib import request


def parse_args():
    parser = argparse.ArgumentParser(description="Summarize observability evidence with Ollama.")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--current-version", required=True)
    parser.add_argument("--rollback-target", required=True)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    return parser.parse_args()


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def fallback_payload(service: str, current_version: str, rollback_target: str) -> dict:
    return {
        "summary": f"Prometheus indicates post-deployment instability for {service}.",
        "proposal": f"Review rollback from {current_version} to {rollback_target}.",
        "confidence": "medium",
        "notes": ["Deterministic rollback target selected from deployment state."],
    }


def call_ollama(prompt: str, model: str, url: str) -> dict:
    req = request.Request(
        f"{url.rstrip('/')}/api/generate",
        data=json.dumps(
            {"model": model, "prompt": prompt, "stream": False, "format": "json"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return json.loads(payload["response"])


def main():
    args = parse_args()
    evidence_dir = Path(args.evidence_dir)
    analysis = read_json(evidence_dir / "analysis_result.json")
    prom = read_text(evidence_dir / "prometheus_infra_signals.json", "{}")
    pods = read_text(evidence_dir / "pod_status_enrichment.json", "[]")
    logs = read_text(evidence_dir / "loki_logs.txt", "No logs")

    prompt = f"""
You are an SRE reviewer preparing a GitHub issue summary.

Service: {args.service}
Current version: {args.current_version}
Deterministic rollback target: {args.rollback_target}

Deterministic analysis:
{json.dumps(analysis, indent=2)}

Prometheus evidence:
{prom[:4000]}

Pod status evidence:
{pods[:3000]}

Recent logs:
{logs[:3000]}

Return JSON only with this exact schema:
{{
  "summary": "1-3 sentence human-readable summary",
  "proposal": "Short rollback proposal sentence",
  "confidence": "low|medium|high",
  "notes": ["short bullet", "short bullet"]
}}

Constraints:
- Do not change the rollback target.
- Treat the rollback target as deterministic input.
- Focus on summarizing risk and rationale for human review.
"""

    fallback = fallback_payload(args.service, args.current_version, args.rollback_target)
    try:
        result = call_ollama(prompt, args.model, args.ollama_url)
        if not isinstance(result, dict):
            result = fallback
    except Exception:
        result = fallback

    result.setdefault("summary", fallback["summary"])
    result.setdefault("proposal", fallback["proposal"])
    result.setdefault("confidence", fallback["confidence"])
    result.setdefault("notes", fallback["notes"])

    output_path = evidence_dir / "llm_proposal.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
