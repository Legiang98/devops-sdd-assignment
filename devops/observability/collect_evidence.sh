#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 6 ]; then
  echo "Usage: $0 <service_name> <namespace> <app_label> <loki_url> <health_endpoint> <output_dir>"
  exit 1
fi

SERVICE_NAME="$1"
NAMESPACE="$2"
APP_LABEL="$3"
LOKI_URL="$4"
HEALTH_ENDPOINT="$5"
OUTPUT_DIR="$6"

mkdir -p "$OUTPUT_DIR"

HEALTH_STATUS_FILE="$OUTPUT_DIR/health_status.json"
HEALTH_BODY_FILE="$OUTPUT_DIR/health_response.txt"
LOKI_RESPONSE_FILE="$OUTPUT_DIR/loki_response.json"
EVIDENCE_SUMMARY_FILE="$OUTPUT_DIR/evidence_summary.json"

health_http_code="$(
  curl -sS -o "$HEALTH_BODY_FILE" -w "%{http_code}" \
    --max-time 15 \
    "$HEALTH_ENDPOINT" || true
)"

python3 - "$HEALTH_STATUS_FILE" "$HEALTH_ENDPOINT" "$health_http_code" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
endpoint = sys.argv[2]
http_code = sys.argv[3]

payload = {
    "endpoint": endpoint,
    "http_status": int(http_code) if http_code.isdigit() else None,
    "reachable": http_code.isdigit(),
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

loki_query="{namespace=\"${NAMESPACE}\"} |= \"${APP_LABEL}\""
loki_query_url="${LOKI_URL%/}/loki/api/v1/query_range"

curl -sS --get \
  --max-time 20 \
  --data-urlencode "query=${loki_query}" \
  --data-urlencode "limit=200" \
  "$loki_query_url" > "$LOKI_RESPONSE_FILE" || printf '{"status":"error","data":{"result":[]}}\n' > "$LOKI_RESPONSE_FILE"

python3 - "$EVIDENCE_SUMMARY_FILE" "$SERVICE_NAME" "$NAMESPACE" "$APP_LABEL" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
service_name = sys.argv[2]
namespace = sys.argv[3]
app_label = sys.argv[4]
root = output_path.parent

health = json.loads((root / "health_status.json").read_text(encoding="utf-8"))
loki = json.loads((root / "loki_response.json").read_text(encoding="utf-8"))
results = ((loki.get("data") or {}).get("result") or []) if isinstance(loki, dict) else []

payload = {
    "service_name": service_name,
    "namespace": namespace,
    "app_label": app_label,
    "health_http_status": health.get("http_status"),
    "health_reachable": health.get("reachable"),
    "loki_result_streams": len(results),
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

echo "Collected evidence into ${OUTPUT_DIR}"
