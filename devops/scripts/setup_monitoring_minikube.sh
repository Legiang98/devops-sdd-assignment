#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MANIFEST_DIR="devops/monitoring/minikube"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required"
  exit 1
fi

if ! command -v minikube >/dev/null 2>&1; then
  echo "minikube CLI is required"
  exit 1
fi

if ! minikube status >/dev/null 2>&1; then
  echo "minikube is not running"
  exit 1
fi

echo "[monitoring] applying manifests"
kubectl apply -f "$MANIFEST_DIR/namespace.yaml"
kubectl apply -f "$MANIFEST_DIR/tempo-configmap.yaml"
kubectl apply -f "$MANIFEST_DIR/tempo.yaml"
kubectl apply -f "$MANIFEST_DIR/otel-collector-configmap.yaml"
kubectl apply -f "$MANIFEST_DIR/otel-collector.yaml"
kubectl apply -f "$MANIFEST_DIR/alloy-configmap.yaml"
kubectl apply -f "$MANIFEST_DIR/alloy.yaml"
kubectl apply -f "$MANIFEST_DIR/grafana-datasource-configmap.yaml"
kubectl apply -f "$MANIFEST_DIR/grafana.yaml"

echo "[monitoring] waiting for rollouts"
kubectl -n monitoring rollout status deploy/tempo --timeout=180s
kubectl -n monitoring rollout status deploy/otel-collector --timeout=180s
kubectl -n monitoring rollout status deploy/alloy --timeout=180s
kubectl -n monitoring rollout status deploy/grafana --timeout=180s

echo "[monitoring] stack is ready"
echo "[monitoring] grafana port-forward: kubectl -n monitoring port-forward svc/grafana 3000:3000"
echo "[monitoring] alloy UI port-forward: kubectl -n monitoring port-forward svc/alloy 12345:12345"
