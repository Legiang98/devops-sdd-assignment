# Kubernetes Manifests

Each microservice gets its own folder under `devops/k8s/`.
Add a new service by creating a new sibling directory with that service's manifests.

Current layout:
- `expense-workflow/`: namespace, deployment, service, ingress, and image tag manifests for the expense service

For Minikube localhost ingress:
- Enable the ingress addon: `minikube addons enable ingress`
- Start a tunnel in a separate terminal: `minikube tunnel`
- Apply [ingress.yaml](/Users/lesip/Projects/side-project/devops-ssd-assignment/devops/k8s/expense-workflow/ingress.yaml)
- Access the service at `http://expense-workflow.localhost`
