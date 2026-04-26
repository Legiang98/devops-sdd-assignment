import argparse
import os
import json
import requests
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="AI Monitoring Agent")
    parser.add_argument("--evidence-dir", required=True, help="Directory containing logs and health data")
    parser.add_argument("--service", required=True)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    return parser.parse_args()

def call_ollama(prompt, model, url):
    endpoint = f"{url}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "format": "json"}
    try:
        response = requests.post(endpoint, json=payload, timeout=60)
        return json.loads(response.json()["response"])
    except Exception as e:
        return {"recommendation": "neutral", "reason": f"AI analysis failed: {str(e)}"}

def main():
    args = parse_args()
    evidence_path = Path(args.evidence_dir)
    
    logs = (evidence_path / "logs.txt").read_text() if (evidence_path / "logs.txt").exists() else "No logs"
    health = (evidence_path / "health.json").read_text() if (evidence_path / "health.json").exists() else "{}"

    prompt = f"""
    You are an SRE Expert. Analyze the following deployment evidence for service '{args.service}':
    
    HEALTH STATUS:
    {health}
    
    RECENT LOGS:
    {logs[:2000]} # Limit logs for prompt size
    
    Task:
    1. Look for Errors, Exceptions, or 5xx status codes.
    2. Evaluate if the service is healthy or failing.
    3. Provide a recommendation: 'stay' or 'rollback'.
    
    Return JSON only:
    {{
      "recommendation": "stay" | "rollback",
      "reason": "short explanation",
      "severity": "low" | "medium" | "high",
      "analysis": "detailed points"
    }}
    """

    print(f"[*] Analyzing evidence for {args.service} using {args.model}...")
    result = call_ollama(prompt, args.model, args.ollama_url)
    
    with open(evidence_path / "analysis_result.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"[!] Recommendation: {result['recommendation'].upper()}")
    print(f"[*] Reason: {result['reason']}")

if __name__ == "__main__":
    main()
