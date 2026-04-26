#!/bin/bash
set -euo pipefail

SERVICE_NAME=$1
NAMESPACE=$2
APP_LABEL=$3
PROMETHEUS_URL=$4
LOKI_URL=$5
HEALTH_URL=$6
OUTPUT_DIR=$7

mkdir -p "$OUTPUT_DIR"

# Tự động trích xuất Base Name để query linh hoạt hơn
# Ví dụ: expense-workflow-service -> expense-workflow
BASE_NAME=$(echo "$APP_LABEL" | sed -E 's/-(service|app|deployment|pod|container)$//')
echo "[*] Derived Base Name: $BASE_NAME (from $APP_LABEL)"

echo "[*] Collecting Health Status from $HEALTH_URL..."
HEALTH_BODY_PATH="$OUTPUT_DIR/health_response_body.txt"
health_http_code=$(curl -sS --connect-timeout 5 -o "$HEALTH_BODY_PATH" -w "%{http_code}" "$HEALTH_URL" || true)
if [ -z "$health_http_code" ] || [ "$health_http_code" = "000" ]; then
  echo '{"http_status": 503, "error": "unreachable"}' > "$OUTPUT_DIR/health_status.json"
else
  HEALTH_BODY_PATH="$HEALTH_BODY_PATH" HEALTH_HTTP_CODE="$health_http_code" python3 - <<'PY' > "$OUTPUT_DIR/health_status.json"
import json
import os
from pathlib import Path

body = Path(os.environ["HEALTH_BODY_PATH"]).read_text(encoding="utf-8")
payload = {
    "http_status": int(os.environ["HEALTH_HTTP_CODE"]),
    "body": body,
}
try:
    payload["json_body"] = json.loads(body)
except json.JSONDecodeError:
    pass

print(json.dumps(payload))
PY
fi

echo "[*] Querying Prometheus (kube-state-metrics) for infra signals..."
# Truy vấn linh hoạt hơn bằng cách dùng BASE_NAME
PROM_QUERY="sum by (reason, pod) (kube_pod_container_status_terminated_reason{namespace=\"$NAMESPACE\", pod=~\".*$BASE_NAME.*\"}) or sum by (reason, pod) (kube_pod_container_status_waiting_reason{namespace=\"$NAMESPACE\", pod=~\".*$BASE_NAME.*\"})"

curl -G -s "$PROMETHEUS_URL/api/v1/query" --data-urlencode "query=$PROM_QUERY" > "$OUTPUT_DIR/prometheus_infra_signals.json" || echo '{"status":"error"}' > "$OUTPUT_DIR/prometheus_infra_signals.json"

echo "[*] Querying Loki logs for $BASE_NAME..."
LOKI_QUERY="{namespace=\"$NAMESPACE\",pod=~\".*$BASE_NAME.*\"}"
LOKI_RESPONSE_PATH="$OUTPUT_DIR/loki_response.json"
query_end_ns=$(($(date +%s) * 1000000000))
query_start_ns=$((query_end_ns - 3600 * 1000000000))

if curl -G -sS "$LOKI_URL/loki/api/v1/query_range" \
  --data-urlencode "query=$LOKI_QUERY" \
  --data-urlencode "start=$query_start_ns" \
  --data-urlencode "end=$query_end_ns" \
  --data-urlencode "limit=200" \
  --data-urlencode "direction=backward" \
  > "$LOKI_RESPONSE_PATH"; then
  if LOKI_RESPONSE_PATH="$LOKI_RESPONSE_PATH" python3 - <<'PY' > "$OUTPUT_DIR/loki_logs.txt"
import json
import os
import sys
from pathlib import Path

payload = json.loads(Path(os.environ["LOKI_RESPONSE_PATH"]).read_text(encoding="utf-8"))
lines = []
for stream in payload.get("data", {}).get("result", []):
    for _, line in stream.get("values", []):
        lines.append(line.rstrip("\n"))

if not lines:
    sys.exit(1)

print("\n".join(lines))
PY
  then
    echo "[*] Loki logs collected via API"
  else
    # Fallback: Lấy log từ kubectl nếu Loki rỗng
    kubectl logs -n "$NAMESPACE" -l "app.kubernetes.io/name" --tail=200 2>/dev/null | grep -i "$BASE_NAME" > "$OUTPUT_DIR/loki_logs.txt" || echo "No logs found via kubectl" > "$OUTPUT_DIR/loki_logs.txt"
  fi
else
  echo "[*] Loki query failed, falling back to kubectl logs..."
  kubectl logs -n "$NAMESPACE" -l "app.kubernetes.io/name" --tail=200 2>/dev/null | grep -i "$BASE_NAME" > "$OUTPUT_DIR/loki_logs.txt" || echo "No logs found via kubectl" > "$OUTPUT_DIR/loki_logs.txt"
fi

echo "[*] Optional: Collecting raw K8s Events for enrichment..."
kubectl get events -n "$NAMESPACE" --field-selector involvedObject.kind=Pod -o json | \
  jq "[.items[] | select(.involvedObject.name | contains(\"$BASE_NAME\"))] | .[0:10]" > "$OUTPUT_DIR/k8s_events_enrichment.json" || echo "[]" > "$OUTPUT_DIR/k8s_events_enrichment.json"

echo "[*] Optional: Collecting detailed Pod Status for enrichment..."
kubectl get pods -n "$NAMESPACE" -o json | \
  jq ".items | map(select(.metadata.name | contains(\"$BASE_NAME\")))" > "$OUTPUT_DIR/pod_status_enrichment.json" || echo "[]" > "$OUTPUT_DIR/pod_status_enrichment.json"

echo "[*] Evidence collection complete in $OUTPUT_DIR"
