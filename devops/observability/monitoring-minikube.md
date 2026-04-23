# Monitoring Stack on Minikube

This setup deploys:
- OpenTelemetry Collector (`otel-collector`)
- Grafana Alloy (`alloy`)
- Grafana Tempo (`tempo`)
- Grafana (`grafana`)

All components run in namespace `monitoring`.

## 1) Deploy stack

```bash
./devops/scripts/setup_monitoring_minikube.sh
```

## 2) Deploy app (if not already)

```bash
kubectl apply -f devops/k8s/namespace.yaml
kubectl apply -f devops/k8s/deployment.yaml
kubectl apply -f devops/k8s/service.yaml
```

The app is configured to export traces to Alloy:
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy.monitoring.svc.cluster.local:4318`

Trace path is:
- App -> Alloy -> OTel Collector -> Tempo -> Grafana

## 3) Open Grafana

```bash
kubectl -n monitoring port-forward svc/grafana 3000:3000
```

Login:
- Username: `admin`
- Password: `admin`

Tempo datasource is provisioned automatically.

## 4) Generate sample traffic

```bash
kubectl -n devops-ssd-assignment port-forward svc/expense-workflow 8000:80
```

Then in another terminal:

```bash
curl -s -X POST http://localhost:8000/expenses \
  -H 'content-type: application/json' \
  -d '{"amount":1500,"description":"laptop"}'

curl -s http://localhost:8000/health
```

## 5) Verify components

```bash
kubectl -n monitoring get pods
kubectl -n monitoring logs deploy/alloy --tail=100
kubectl -n monitoring logs deploy/otel-collector --tail=100
kubectl -n monitoring logs deploy/tempo --tail=100
```

In Grafana Explore, select `Tempo` datasource and search traces for service `expense-workflow`.

## Notes

- This is local-first and intentionally minimal.
- No ingress is used; use `kubectl port-forward` in Minikube.
- Grafana credentials are plain text for local development only.
- GitOps option with Argo CD: apply `devops/argocd/monitoring-application.yaml`.
