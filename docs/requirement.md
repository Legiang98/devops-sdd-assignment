# DevOps for AI-First Enterprise Applications: Assignment Requirements

## Overview
We want to understand how you'd approach DevOps for enterprise business applications in a world where AI agents and specifications are first-class participants in the software lifecycle. We're less interested in a specific tech stack and more interested in how you think, what tradeoffs you make, and whether you can turn an idea into something that actually runs.

### Tooling Constraint
**Please use open-source tools throughout.** Hosted model APIs are fine if they sit behind an open-source gateway, but the rest of the stack—whether it's agent orchestration, policy, or observability—should be open.

---

## Part 1: Target-State Design

Imagine a fictional mid-sized enterprise:
- **Team**: ~5 engineers.
- **Applications**: ~20 business applications (internal tools, customer-facing web apps, workflow systems).
- **Environment**: Multiple environments.
- **Compliance**: SOC 2 + GDPR in scope.

Design what "good DevOps" should look like for them 6 months from now, assuming agents and specs are part of the daily workflow.

### Coverage Requirements
Your design should cover:
- **Lifecycle**: How a requirement becomes a running, observed, auditable change. Define who (or what) performs each step.
- **Building Blocks**: Open-source components for agentic coding, IaC / GitOps, policy-as-code, observability, and evaluation. Briefly note why you chose these over alternatives.
- **Human–Agent Boundary**: Define what agents do autonomously, what they do under review, and what they never do based on risk assessment.
- **Governance**: How the system produces audit evidence natively rather than as an afterthought.
- **Rollout Risks**: Anticipated friction points or failures, and metrics to measure success.

**Format**: 4–6 pages of Markdown. Diagrams (ASCII, Mermaid, or images) are welcome. **Short and sharp beats long and thorough.**

---

## Part 2: Proof of Concept (PoC)

Build a small, runnable vertical slice that demonstrates the core of your design. Scope it narrowly—one change flowing through the pipeline is sufficient.

### PoC Requirements
Demonstrate the following:
1.  **Specification**: A versioned, reviewable artifact for a realistic change (e.g., "add an approval step to an expense workflow" or "expose a new read endpoint").
2.  **Agent Integration**: An open-source agent that consumes the spec and produces implementation/deployment artifacts.
3.  **Policy/Quality Gate**: At least one gate between agent output and the environment. Show it catching a real issue during the demo.
4.  **Running Deployment**: A local deployment is acceptable.
5.  **Observability**: Telemetry that proves the change behaves as described in the spec.
6.  **Rollback**: A demonstrable rollback path.

---

## Deliverables

1.  **Git Repository**: A link or zip containing the code and a `README` for running the PoC.
2.  **Specifications**: The spec(s) used in the PoC.
3.  **ADR-style Note**: A 1-page note listing tools chosen and alternatives ruled out.
4.  **Demo Video**: A 5–10 minute screen recording walking through the demo end-to-end, including the gate and rollback.