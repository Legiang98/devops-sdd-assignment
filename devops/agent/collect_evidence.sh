#!/bin/bash
set -euo pipefail

SERVICE_NAME=$1
NAMESPACE=$2
LOKI_URL=$3
HEALTH_URL=$4
OUTPUT_DIR=$5

mkdir -p "$OUTPUT_DIR"

echo "[*] Collecting Health Status from $HEALTH_URL..."
curl -s -o "$OUTPUT_DIR/health.json" "$HEALTH_URL" || echo '{"status": "unreachable"}' > "$OUTPUT_DIR/health.json"

echo "[*] Querying Loki logs for service $SERVICE_NAME in $NAMESPACE..."
# Giả lập query Loki (trong thực tế sẽ dùng logcli hoặc curl tới Loki API)
# Ở đây chúng ta lấy log trực tiếp từ kubectl để làm bằng chứng cho PoC
kubectl logs -n "$NAMESPACE" -l "app.kubernetes.io/name=$SERVICE_NAME" --tail=100 > "$OUTPUT_DIR/logs.txt" || echo "No logs found" > "$OUTPUT_DIR/logs.txt"

echo "[*] Evidence collection complete in $OUTPUT_DIR"
