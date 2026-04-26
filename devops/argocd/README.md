# Argo CD

GitOps handoff from Git to cluster via Argo CD Applications.

Canonical Kubernetes-facing manifests now live under `devops/k8s/argocd/`.

## Bootstrap Flow

- `application.yaml`: parent app-of-apps bootstrap. It points Argo CD at `devops/k8s/argocd`.
- Child `Application` manifests under `devops/k8s/argocd/` then manage each service or platform slice.

## Apply

```bash
kubectl apply -f devops/argocd/application.yaml
```

After that, Argo CD should sync:
- `namespace.yaml`
- `repo-secret.yaml`
- `ingress.yaml`
- `*-application.yaml` child apps such as `expense-workflow-service-application.yaml`, `invoice-workflow-service-application.yaml`, and `observability-application.yaml`
