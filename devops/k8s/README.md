# Kubernetes Manifests

Each microservice gets its own folder under `devops/k8s/`.
Add a new service by creating a new sibling directory with that service's manifests.

Current layout:
- `argocd/`: namespace, ingress, repository secret, and `Application` manifests for Argo CD bootstrap
- `expense-workflow-service/`: namespace, deployment, service, ingress, and image tag manifests for the expense service
- `invoice-workflow-service/`: namespace, deployment, service, ingress, and image tag manifests for the invoice workflow service

For Minikube localhost ingress:
- Enable the ingress addon: `minikube addons enable ingress`
- Start a tunnel in a separate terminal: `minikube tunnel`
- Apply [ingress.yaml](/Users/lesip/Projects/side-project/devops-ssd-assignment/devops/k8s/expense-workflow-service/ingress.yaml)
- Access the service at `http://expense-workflow-service.192.168.49.2.nip.io`

Current ingress status:
- `expense-workflow-service`: ingress is generated from spec and currently disabled because the spec sets `deployment.k8s.ingress.enabled: false`
- `invoice-workflow-service`: ingress is generated as a real `Ingress` because the spec sets `deployment.k8s.ingress.enabled: true`
- `argocd`: ingress host is `http://argocd.192.168.49.2.nip.io` and assumes Argo CD core is already installed
