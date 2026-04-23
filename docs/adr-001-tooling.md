# ADR-001: Tooling Choices for Spec-Driven DevOps PoC

## Status
Accepted

## Context
The assignment requires:
- open-source-first stack,
- spec-driven lifecycle,
- agent-generated artifacts,
- policy gate,
- observability proof,
- demonstrable rollback,
- local runnable setup.

## Decision
Use a lightweight Python stack:
- FastAPI app as business service surface.
- YAML spec artifacts in Git.
- Custom open-source agent workflow script (`devops/agent/run_agent.py`) to generate release artifacts.
- Policy gate script (`devops/policy/check_spec_alignment.py`) as pre-deployment control.
- Prometheus metrics endpoint and verification script for runtime conformance.
- Docker Compose local deployment and symlink-based release promotion/rollback.

## Rationale
- Minimizes setup while preserving the target architecture pattern.
- Keeps every control visible and auditable in repository artifacts.
- Easy for reviewers to run and reproduce.

## Alternatives Considered
1. Kubernetes + ArgoCD + OPA Gatekeeper
- Pros: strong production alignment.
- Rejected for PoC: too infrastructure-heavy for one change flow.

2. Closed SaaS coding/deploy agent
- Pros: faster feature richness.
- Rejected: assignment prioritizes open-source agent/tooling.

3. Runtime-only policy controls
- Pros: centralized enforcement.
- Rejected: assignment asks for gate between generated output and deployment; pre-deploy checks give earlier feedback.

4. Full tracing stack (OTel collector + Tempo/Jaeger)
- Pros: richer observability.
- Rejected for initial slice: unnecessary for proving behavior from telemetry alone.

## Consequences
- PoC is intentionally narrow but clear and testable.
- Agent logic is deterministic by default; LLM-backed mode can be introduced later behind an open-source gateway without changing overall architecture.
