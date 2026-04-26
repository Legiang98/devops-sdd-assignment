# Argo CD Manifests

Kubernetes-facing Argo CD manifests live here.

Included:
- `namespace.yaml`: Argo CD namespace
- `ingress.yaml`: localhost ingress for `argocd-server`
- `repo-secret.yaml`: repository credential secret for Argo CD
- `expense-workflow-service-application.yaml`: GitOps application for the expense service
- `invoice-workflow-service-application.yaml`: GitOps application for the invoice workflow service
- `observability-application.yaml`: GitOps application for the observability stack

Notes:
- `devops/argocd/application.yaml` is the parent app-of-apps bootstrap and should be applied manually once.
- This directory is the parent app source path. Argo CD will sync everything in it, including child `Application` resources.
- This folder assumes Argo CD core components are already installed in the `argocd` namespace.
- The ingress assumes an `argocd-server` Service already exists from the Argo CD installation.
- For Minikube localhost access, enable the ingress addon and run `minikube tunnel`.
- Argo CD UI host: `http://argocd.192.168.49.2.nip.io`
