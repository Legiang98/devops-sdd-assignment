import argparse
from pathlib import Path

import yaml


DEFAULT_MANIFEST_TOGGLES = {
    "namespace.yaml": True,
    "deployment.yaml": True,
    "service.yaml": True,
    "ingress.yaml": True,
    "image-tag.yaml": True,
    "post-deploy-evaluation-job.yaml": True,
}

ARGOCD_NAMESPACE = "argocd"
POST_DEPLOY_TRIGGER_SECRET_NAME = "gha-post-deployment-trigger"
POST_DEPLOY_TRIGGER_SECRET_KEY = "pat"
OBSERVABILITY_WORKFLOW_REF = "feat/post-deployment"
POST_DEPLOY_ENV_CONFIGMAP_NAME = "post-deployment-evaluation-env"
PROMETHEUS_URL_ENV_NAME = "PROMETHEUS_URL"
LOKI_URL_ENV_NAME = "LOKI_URL"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Deterministic GitOps manifest scaffold generator"
    )
    parser.add_argument("--spec", required=True, help="Path to the changed spec file")
    parser.add_argument("--output-dir", required=True, help="Directory to save manifests")
    parser.add_argument(
        "--model",
        default="qwen2.5:7b",
        help="Deprecated compatibility argument; ignored",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://127.0.0.1:11434",
        help="Deprecated compatibility argument; ignored",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def dump_yaml(document: dict) -> str:
    return yaml.safe_dump(document, sort_keys=False)


def resolve_application_root(spec_path: Path) -> Path:
    specs_dir = spec_path.parent
    if specs_dir.name != "specs":
        raise ValueError(f"Expected spec under an application specs directory: {spec_path}")
    return specs_dir.parent


def find_baseline_spec(app_root: Path) -> Path:
    specs_dir = app_root / "specs"
    candidates = sorted(specs_dir.glob("*BASELINE*.y*ml"))
    if not candidates:
        raise FileNotFoundError(f"No baseline spec found under {specs_dir}")

    exact_baseline = specs_dir / "BASELINE.yaml"
    if exact_baseline.exists():
        return exact_baseline

    return candidates[0]


def manifest_toggles(baseline_spec: dict) -> dict[str, bool]:
    toggles = dict(DEFAULT_MANIFEST_TOGGLES)
    k8s_spec = baseline_spec.get("deployment", {}).get("k8s", {})
    ingress_enabled = k8s_spec.get("ingress", {}).get("enabled")
    if ingress_enabled is not None:
        toggles["ingress.yaml"] = bool(ingress_enabled)
    return toggles


def required_manifest_files(baseline_spec: dict) -> list[str]:
    toggles = manifest_toggles(baseline_spec)
    return [filename for filename, enabled in toggles.items() if enabled]


def manifest_status(output_dir: Path, baseline_spec: dict) -> tuple[bool, list[str]]:
    required_files = required_manifest_files(baseline_spec)
    missing = [name for name in required_files if not (output_dir / name).exists()]
    return not missing, missing


def app_slug(app_root: Path, baseline_spec: dict) -> str:
    workspace = baseline_spec.get("workspace", {})
    workspace_path = workspace.get("path")
    if workspace_path:
        return Path(workspace_path).name
    return app_root.name


def service_name(app_root: Path, baseline_spec: dict) -> str:
    deployment_spec = baseline_spec.get("deployment", {}).get("k8s", {})
    deployment_name = deployment_spec.get("deployment", {}).get("name")
    service_name_value = deployment_spec.get("service", {}).get("name")
    return deployment_name or service_name_value or baseline_spec.get("service") or app_root.name


def service_resource_name(app_root: Path, baseline_spec: dict) -> str:
    deployment_spec = baseline_spec.get("deployment", {}).get("k8s", {})
    service_name_value = deployment_spec.get("service", {}).get("name")
    return service_name_value or service_name(app_root, baseline_spec)


def namespace_name(baseline_spec: dict) -> str:
    return (
        baseline_spec.get("deployment", {})
        .get("k8s", {})
        .get("namespace", "default")
    )


def container_port(baseline_spec: dict) -> int:
    return int(
        baseline_spec.get("deployment", {})
        .get("k8s", {})
        .get("deployment", {})
        .get("container_port", 8000)
    )


def service_port(baseline_spec: dict) -> int:
    return int(
        baseline_spec.get("deployment", {})
        .get("k8s", {})
        .get("service", {})
        .get("port", 80)
    )


def target_port(baseline_spec: dict) -> int:
    return int(
        baseline_spec.get("deployment", {})
        .get("k8s", {})
        .get("service", {})
        .get("target_port", container_port(baseline_spec))
    )


def replica_count(baseline_spec: dict) -> int:
    return int(
        baseline_spec.get("deployment", {})
        .get("k8s", {})
        .get("deployment", {})
        .get("replicas", 1)
    )


def ingress_host(app_slug_value: str) -> str:
    return f"{app_slug_value}.local"


def change_id_value(baseline_spec: dict) -> str:
    return str(baseline_spec.get("change_id", "BASELINE"))


def health_endpoint(workload_name: str, namespace: str) -> str:
    return f"http://{workload_name}.{namespace}.svc.cluster.local/health"


def render_namespace(namespace: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
        },
    }


def render_deployment(
    namespace: str,
    app_slug_value: str,
    workload_name: str,
    replicas: int,
    port: int,
) -> dict:
    labels = {
        "app": workload_name,
        "app.kubernetes.io/name": app_slug_value,
        "app.kubernetes.io/managed-by": "gitops-agent",
    }
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": workload_name,
            "namespace": namespace,
            "labels": dict(labels),
        },
        "spec": {
            "replicas": replicas,
            "selector": {
                "matchLabels": {
                    "app": workload_name,
                }
            },
            "template": {
                "metadata": {
                    "labels": dict(labels),
                },
                "spec": {
                    "containers": [
                        {
                            "name": workload_name,
                            "image": f"{app_slug_value}:latest",
                            "ports": [{"containerPort": port}],
                            "livenessProbe": {
                                "httpGet": {"path": "/healthz", "port": port},
                                "initialDelaySeconds": 30,
                                "periodSeconds": 10,
                            },
                            "readinessProbe": {
                                "httpGet": {"path": "/readiness", "port": port},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 10,
                            },
                        }
                    ]
                },
            },
        },
    }


def render_service(
    namespace: str,
    workload_name: str,
    service_name_value: str,
    port: int,
    target_port_value: int,
) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service_name_value,
            "namespace": namespace,
            "labels": {
                "app": workload_name,
            },
        },
        "spec": {
            "selector": {
                "app": workload_name,
            },
            "ports": [
                {
                    "protocol": "TCP",
                    "port": port,
                    "targetPort": target_port_value,
                }
            ],
        },
    }


def render_ingress(
    namespace: str,
    app_slug_value: str,
    workload_name: str,
    service_name_value: str,
    service_port_value: int,
) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": f"{workload_name}-ingress",
            "namespace": namespace,
            "annotations": {
                "kubernetes.io/ingress.class": "nginx",
            },
            "labels": {
                "app": workload_name,
            },
        },
        "spec": {
            "rules": [
                {
                    "host": ingress_host(app_slug_value),
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": service_name_value,
                                        "port": {"number": service_port_value},
                                    }
                                },
                            }
                        ]
                    },
                }
            ]
        },
    }


def render_image_tag(app_slug_value: str) -> str:
    return (
        "# Auto-generated scaffold for CI image updates.\n"
        "image:\n"
        f"  repository: {app_slug_value}\n"
        "  tag: latest\n"
    )


def render_post_deploy_evaluation_job(
    namespace: str,
    app_slug_value: str,
    workload_name: str,
    change_id: str,
) -> dict:
    workflow_url = (
        "https://api.github.com/repos/Legiang98/devops-sdd-assignment/"
        "actions/workflows/observability-workflow.yml/dispatches"
    )
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"{app_slug_value}-post-deploy-evaluation",
            "namespace": ARGOCD_NAMESPACE,
            "annotations": {
                "argocd.argoproj.io/hook": "PostSync",
                "argocd.argoproj.io/hook-delete-policy": "BeforeHookCreation,HookSucceeded",
            },
        },
        "spec": {
            "ttlSecondsAfterFinished": 600,
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/name": app_slug_value,
                        "app.kubernetes.io/component": "post-deploy-evaluation",
                    }
                },
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "trigger-observability",
                            "image": "curlimages/curl:8.7.1",
                            "env": [
                                {"name": "SERVICE_NAME", "value": app_slug_value},
                                {"name": "APP_NAMESPACE", "value": namespace},
                                {"name": "APP_LABEL", "value": workload_name},
                                {"name": "CHANGE_ID", "value": change_id},
                                {"name": "CURRENT_VERSION", "value": "latest"},
                                {"name": "PREVIOUS_HEALTHY_VERSION", "value": "unknown"},
                                {"name": "ARGOCD_APP_NAME", "value": app_slug_value},
                                {
                                    "name": "GITHUB_TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": POST_DEPLOY_TRIGGER_SECRET_NAME,
                                            "key": POST_DEPLOY_TRIGGER_SECRET_KEY,
                                        }
                                    },
                                },
                                {
                                    "name": "HEALTH_ENDPOINT",
                                    "value": health_endpoint(workload_name, namespace),
                                },
                                {
                                    "name": PROMETHEUS_URL_ENV_NAME,
                                    "valueFrom": {
                                        "configMapKeyRef": {
                                            "name": POST_DEPLOY_ENV_CONFIGMAP_NAME,
                                            "key": PROMETHEUS_URL_ENV_NAME,
                                        }
                                    },
                                },
                                {
                                    "name": LOKI_URL_ENV_NAME,
                                    "valueFrom": {
                                        "configMapKeyRef": {
                                            "name": POST_DEPLOY_ENV_CONFIGMAP_NAME,
                                            "key": LOKI_URL_ENV_NAME,
                                        }
                                    },
                                },
                                {
                                    "name": "OBSERVABILITY_WORKFLOW_URL",
                                    "value": workflow_url,
                                },
                                {
                                    "name": "OBSERVABILITY_WORKFLOW_REF",
                                    "value": OBSERVABILITY_WORKFLOW_REF,
                                },
                            ],
                            "command": ["/bin/sh", "-ec"],
                            "args": [
                                "\n".join(
                                    [
                                        'test -n "${GITHUB_TOKEN}"',
                                        'cat > /tmp/dispatch.json <<EOF',
                                        "{",
                                        '  "ref": "${OBSERVABILITY_WORKFLOW_REF}",',
                                        '  "inputs": {',
                                        '    "service_name": "${SERVICE_NAME}",',
                                        '    "namespace": "${APP_NAMESPACE}",',
                                        '    "app_label": "${APP_LABEL}",',
                                        '    "change_id": "${CHANGE_ID}",',
                                        '    "current_version": "${CURRENT_VERSION}",',
                                        '    "previous_healthy_version": "${PREVIOUS_HEALTHY_VERSION}",',
                                        '    "argocd_app_name": "${ARGOCD_APP_NAME}",',
                                        f'    "prometheus_url": "${{{PROMETHEUS_URL_ENV_NAME}}}",',
                                        f'    "loki_url": "${{{LOKI_URL_ENV_NAME}}}",',
                                        '    "health_endpoint": "${HEALTH_ENDPOINT}"',
                                        "  }",
                                        "}",
                                        "EOF",
                                        'http_code=$(curl -sS -o /tmp/dispatch-response.txt -w "%{http_code}" \\',
                                        '  -X POST \\',
                                        '  -H "Accept: application/vnd.github+json" \\',
                                        '  -H "Authorization: Bearer ${GITHUB_TOKEN}" \\',
                                        '  -H "X-GitHub-Api-Version: 2022-11-28" \\',
                                        '  "${OBSERVABILITY_WORKFLOW_URL}" \\',
                                        '  --data @/tmp/dispatch.json)',
                                        'if [ "${http_code}" != "204" ]; then',
                                        '  cat /tmp/dispatch-response.txt',
                                        '  echo "GitHub workflow dispatch failed with status ${http_code}"',
                                        '  exit 1',
                                        "fi",
                                        'echo "Triggered observability workflow for ${SERVICE_NAME} (${CHANGE_ID}) on ref ${OBSERVABILITY_WORKFLOW_REF}"',
                                    ]
                                )
                            ],
                        }
                    ],
                },
            },
            "backoffLimit": 1,
        },
    }


def build_manifest_bundle(app_root: Path, baseline_spec: dict) -> dict[str, str]:
    toggles = manifest_toggles(baseline_spec)
    app_slug_value = app_slug(app_root, baseline_spec)
    workload_name = service_name(app_root, baseline_spec)
    service_name_value = service_resource_name(app_root, baseline_spec)
    namespace = namespace_name(baseline_spec)
    deployment_port = container_port(baseline_spec)
    svc_port = service_port(baseline_spec)
    svc_target_port = target_port(baseline_spec)
    replicas = replica_count(baseline_spec)
    change_id = change_id_value(baseline_spec)

    manifest_bundle = {
        "namespace.yaml": dump_yaml(render_namespace(namespace)),
        "deployment.yaml": dump_yaml(
            render_deployment(
                namespace=namespace,
                app_slug_value=app_slug_value,
                workload_name=workload_name,
                replicas=replicas,
                port=deployment_port,
            )
        ),
        "service.yaml": dump_yaml(
            render_service(
                namespace=namespace,
                workload_name=workload_name,
                service_name_value=service_name_value,
                port=svc_port,
                target_port_value=svc_target_port,
            )
        ),
        "ingress.yaml": dump_yaml(
            render_ingress(
                namespace=namespace,
                app_slug_value=app_slug_value,
                workload_name=workload_name,
                service_name_value=service_name_value,
                service_port_value=svc_port,
            )
        ),
        "image-tag.yaml": render_image_tag(app_slug_value),
        "post-deploy-evaluation-job.yaml": dump_yaml(
            render_post_deploy_evaluation_job(
                namespace=namespace,
                app_slug_value=app_slug_value,
                workload_name=workload_name,
                change_id=change_id,
            )
        ),
    }
    return {
        filename: content
        for filename, content in manifest_bundle.items()
        if toggles.get(filename, True)
    }


def scaffold_manifests(output_dir: Path, manifest_bundle: dict[str, str]) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written_files = []
    for filename, content in manifest_bundle.items():
        path = output_dir / filename
        if path.exists():
            continue
        path.write_text(content, encoding="utf-8")
        written_files.append(filename)
    return written_files


def main():
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    output_dir = Path(args.output_dir).resolve()
    app_root = resolve_application_root(spec_path)
    baseline_path = find_baseline_spec(app_root)
    baseline_spec = load_yaml(baseline_path)

    complete, missing_files = manifest_status(output_dir, baseline_spec)
    if complete:
        print(f"[*] GitOps manifests already exist for {app_root.name} at {output_dir}. Skipping.")
        return

    manifest_bundle = build_manifest_bundle(app_root, baseline_spec)

    if output_dir.exists():
        print(
            f"[*] Existing GitOps directory found for {app_root.name}, "
            f"backfilling missing files: {', '.join(missing_files)}"
        )
    else:
        print(
            f"[*] No GitOps directory found for {app_root.name}. "
            f"Generating deterministic scaffold from {baseline_path.name}."
        )

    written_files = scaffold_manifests(output_dir, manifest_bundle)
    if written_files:
        for filename in written_files:
            print(f"[+] Generated: {output_dir / filename}")
    else:
        print("[*] No files written. Existing manifests were preserved.")


if __name__ == "__main__":
    main()
