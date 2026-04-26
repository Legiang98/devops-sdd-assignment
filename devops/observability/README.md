# Post-Deployment Observability Flow

This directory contains the tools for AI-driven post-deployment evaluation.

## Components

1.  **`collect_evidence.sh`**: A shell script that gathers logs (via `kubectl`) and health status (via `curl`) from the deployed service.
2.  **`monitor_agent.py`**: A Python-based AI agent that analyzes the collected evidence using **Ollama (Qwen2.5)**.
3.  **`observability-workflow.yml`**: The GitHub Actions workflow that orchestrates the evaluation.

## Logic Flow

1.  **Trigger**: Manually or via an automated post-sync hook from ArgoCD.
2.  **Context capture**: Saves deployment context such as service, change ID, app name, current version, and previous healthy version.
3.  **Collection**: Gathers health signals and Loki logs from the live environment.
4.  **Analysis**: AI evaluates the data and produces a rollback recommendation only when the evidence is strong enough.
4.  **Reporting**: 
    - If healthy: Workflow completes, evidence is uploaded as artifacts.
    - If unstable: AI recommends a **rollback** and creates a GitHub Issue with full evidence for human review.

## Security & Governance

The AI Agent is **read-only**. It identifies risks but never performs the rollback itself. Rollback execution is handled by a separate approval-gated workflow to maintain human oversight.

## Argo CD Hook Placement

- Put the post-deployment hook manifest in each child application source path, for example:
  - `devops/k8s/expense-workflow-service/post-deploy-evaluation-job.yaml`
  - `devops/k8s/invoice-workflow-service/post-deploy-evaluation-job.yaml`
- Annotate the Job with `argocd.argoproj.io/hook: PostSync`.
- Run the hook Job in namespace `argocd` even though it evaluates workloads in the target application namespace.
- Provide a PAT in secret `gha-post-deployment-trigger` with key `pat` in namespace `argocd` so the hook can trigger GitHub Actions.
- The hook dispatches `.github/workflows/observability-workflow.yml` through GitHub's `workflow_dispatch` API and currently targets ref `feat/post-deployment`.
- The hook should hand off to an external evaluator or workflow; it should not perform rollback itself.

## PoC Note

- This workflow is evaluation-only.
- It collects evidence into `./evidence`, uploads artifacts, and opens a rollback recommendation issue only when the agent returns `rollback`.
- It does not deploy, revert Git, or execute rollback.
