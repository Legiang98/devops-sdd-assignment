# Argo CD

GitOps handoff from Git to cluster via Argo CD Applications.

## Applications

- `application.yaml`: deploys business service manifests from `devops/k8s` into namespace `devops-ssd-assignment`.
- `monitoring-application.yaml`: deploys monitoring stack from `devops/monitoring/minikube` into namespace `monitoring`.

## Apply

```bash
kubectl apply -f devops/argocd/application.yaml
kubectl apply -f devops/argocd/monitoring-application.yaml
```
