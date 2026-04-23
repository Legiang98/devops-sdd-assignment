#!/usr/bin/env python
import argparse
import json
import re
import urllib.request


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_text(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8")


def metric_value(metrics_text: str, metric: str, labels: dict[str, str] | None = None) -> float:
    if labels:
        label_part = ",".join(f'{k}="{v}"' for k, v in labels.items())
        pattern = rf"^{re.escape(metric)}\{{{re.escape(label_part)}\}}\s+([0-9.]+)$"
    else:
        pattern = rf"^{re.escape(metric)}\s+([0-9.]+)$"

    for line in metrics_text.splitlines():
        m = re.match(pattern, line)
        if m:
            return float(m.group(1))
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    low = post_json(f"{base}/expenses", {"amount": 800, "description": "Keyboard"})
    high = post_json(f"{base}/expenses", {"amount": 2000, "description": "Team offsite"})

    post_json(f"{base}/expenses/{low['id']}/approve", {"role": "manager"})
    post_json(f"{base}/expenses/{high['id']}/approve", {"role": "manager"})
    post_json(f"{base}/expenses/{high['id']}/approve", {"role": "finance"})

    metrics = get_text(f"{base}/metrics")

    manager_required = metric_value(metrics, "approval_step_required_total", {"step": "manager"})
    finance_required = metric_value(metrics, "approval_step_required_total", {"step": "finance"})
    approved_total = metric_value(metrics, "expense_approved_total")

    if manager_required < 2:
        raise SystemExit("Expected manager required count >= 2")
    if finance_required < 1:
        raise SystemExit("Expected finance required count >= 1")
    if approved_total < 2:
        raise SystemExit("Expected approved expense count >= 2")

    print("Telemetry verification passed")
    print(f"manager_required={manager_required}")
    print(f"finance_required={finance_required}")
    print(f"expense_approved_total={approved_total}")


if __name__ == "__main__":
    main()
