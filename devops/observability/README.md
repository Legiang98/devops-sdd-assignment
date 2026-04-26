# Post-Deployment Evaluation (Prometheus Driven)

This directory contains the evaluation logic for post-deployment health checks.

## Why Prometheus / kube-state-metrics?

We prefer Prometheus metrics over raw Kubernetes Events for the following reasons:
1.  **Quantitative Signals**: Metrics provide a count and duration, allowing for threshold-based analysis (e.g., "more than 3 restarts in 5 minutes").
2.  **Historical State**: Events are transient and often deleted after 1 hour. Metrics allow us to see the state of the pod even if the event has aged out.
3.  **Deterministic Failure Reasons**: `kube_pod_container_status_waiting_reason` provides clear, machine-readable labels like `CrashLoopBackOff` or `ImagePullBackOff` without parsing raw event strings.
4.  **Scalability**: Querying Prometheus is more efficient than scanning hundreds of events across a namespace.

## Evidence Files
- `health_status.json`: Results of the HTTP health check.
- `prometheus_infra_signals.json`: Core infrastructure signals from kube-state-metrics.
- `loki_logs.txt`: Application logs for deep-dive analysis.
- `k8s_events_enrichment.json`: Raw events used only for additional context.
