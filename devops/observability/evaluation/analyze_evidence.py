#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze post-deployment evidence via Prometheus signals")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--service", required=True)
    return parser.parse_args()

def read_json(path):
    if not path.exists(): return {}
    try: return json.loads(path.read_text())
    except: return {}

def analyze_prometheus(prom_data):
    findings = []
    critical_signals = ["CrashLoopBackOff", "OOMKilled", "Error", "ContainerCreating"]
    
    results = prom_data.get("data", {}).get("result", [])
    for res in results:
        reason = res.get("metric", {}).get("reason")
        value = res.get("value", [0, "0"])[1]
        if int(value) > 0:
            findings.append(f"Metric Signal: {reason} detected (count: {value})")
            if reason in ["CrashLoopBackOff", "OOMKilled", "Error"]:
                return True, findings # Strong signal for rollback
    
    return False, findings

def main():
    args = parse_args()
    ev = Path(args.evidence_dir)
    
    health = read_json(ev / "health_status.json")
    prom = read_json(ev / "prometheus_infra_signals.json")
    
    rollback_needed = False
    analysis_points = []
    
    # 1. Check Health
    if health.get("http_status") != 200:
        rollback_needed = True
        analysis_points.append(f"❌ Health check failed with status {health.get('http_status')}")

    # 2. Check Prometheus Metrics (Primary Source)
    infra_fail, infra_findings = analyze_prometheus(prom)
    analysis_points.extend(infra_findings)
    if infra_fail:
        rollback_needed = True
        analysis_points.append("❌ Critical infrastructure failure detected via Prometheus metrics.")

    result = {
        "service": args.service,
        "recommendation": "rollback" if rollback_needed else "stay",
        "severity": "high" if rollback_needed else "low",
        "reason": "Critical failure detected in health or infra metrics." if rollback_needed else "Service appears stable.",
        "analysis": "\n".join(analysis_points)
    }
    
    (ev / "analysis_result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
