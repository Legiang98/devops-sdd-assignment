# Argo CD

GitOps handoff from Git to cluster via Argo CD Applications.

Canonical Kubernetes-facing manifests now live under `devops/k8s/argocd/`.

## Applications

- `application.yaml`: deploys the expense service manifests from `devops/k8s/expense-workflow` into namespace `devops-ssd-assignment`.
- `observability-application.yaml`: deploys the observability stack from `devops/observability/minikube` into namespace `monitoring`.

## Apply

```bash
kubectl apply -f devops/argocd/application.yaml
kubectl apply -f devops/argocd/observability-application.yaml
```
