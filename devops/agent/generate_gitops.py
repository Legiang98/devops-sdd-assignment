import argparse
import os
import json
import requests
import yaml
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="GitOps Manifest Generator Agent")
    parser.add_argument("--spec", required=True, help="Path to the spec file")
    parser.add_argument("--output-dir", required=True, help="Directory to save manifests")
    parser.add_argument("--model", default="qwen2.5:7b", help="Ollama model name")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama API URL")
    return parser.parse_args()

def call_ollama(prompt, model, url):
    endpoint = f"{url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    response = requests.post(endpoint, json=payload)
    response.raise_for_status()
    return json.loads(response.json()["response"])

def main():
    args = parse_args()
    spec_path = Path(args.spec)
    output_dir = Path(args.output_dir)
    
    with open(spec_path, "r") as f:
        spec_content = yaml.safe_load(f)

    app_name = spec_content.get("service") or spec_content.get("application", {}).get("name") or output_dir.name
    
    print(f"[*] Analyzing spec for application: {app_name}")
    
    # Check if infrastructure exists
    is_new_app = not output_dir.exists()
    if is_new_app:
        print(f"[!] Application {app_name} does not exist in GitOps folder. Initializing...")
        output_dir.mkdir(parents=True, exist_ok=True)

    prompt = f"""
    You are a Senior K8s Expert. Generate Kubernetes manifests for the application '{app_name}' based on the following spec:
    
    {yaml.dump(spec_content)}
    
    Requirements:
    1. Generate Deployment, Service, and Ingress.
    2. Use standard labels: app={app_name}.
    3. Include health checks (Liveness/Readiness).
    4. For Ingress, assume host is {app_name}.local.
    
    Return a JSON object where keys are filenames (e.g., 'deployment.yaml') and values are the file contents.
    Example:
    {{
      "deployment.yaml": "apiVersion: apps/v1\\nkind: Deployment...",
      "service.yaml": "..."
    }}
    """

    print(f"[*] Requesting manifest generation from {args.model}...")
    manifests = call_ollama(prompt, args.model, args.ollama_url)

    for filename, content in manifests.items():
        file_path = output_dir / filename
        file_path.write_text(content)
        print(f"[+] Generated: {file_path}")

    print("[*] Manifest generation complete.")

if __name__ == "__main__":
    main()
