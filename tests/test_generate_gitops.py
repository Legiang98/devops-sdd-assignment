import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from devops.agent.generate_gitops import (
    build_manifest_bundle,
    find_baseline_spec,
    manifest_status,
    required_manifest_files,
    scaffold_argocd_application,
    scaffold_manifests,
)


class GenerateGitOpsTests(unittest.TestCase):
    def test_find_baseline_prefers_exact_baseline_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_root = Path(tmpdir) / "applications" / "sample-service"
            specs_dir = app_root / "specs"
            specs_dir.mkdir(parents=True)
            (specs_dir / "ZZZ-BASELINE.yaml").write_text("service: sample-service\n", encoding="utf-8")
            exact = specs_dir / "BASELINE.yaml"
            exact.write_text("service: sample-service\n", encoding="utf-8")

            self.assertEqual(find_baseline_spec(app_root), exact)

    def test_scaffold_generates_required_files_without_overwriting_existing(self):
        baseline_spec = {
            "service": "invoice-workflow-service",
            "workspace": {"path": "applications/invoice-workflow-service"},
            "deployment": {
                "k8s": {
                    "namespace": "devops-ssd-assignment",
                    "deployment": {
                        "name": "invoice-workflow-service",
                        "replicas": 1,
                        "container_port": 8000,
                    },
                    "service": {
                        "name": "invoice-workflow-service",
                        "port": 80,
                        "target_port": 8000,
                    },
                    "ingress": {
                        "enabled": True,
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            app_root = Path(tmpdir) / "applications" / "invoice-workflow-service"
            output_dir = Path(tmpdir) / "devops" / "k8s" / "invoice-workflow-service"
            output_dir.mkdir(parents=True)
            existing_deployment = output_dir / "deployment.yaml"
            existing_deployment.write_text("existing deployment", encoding="utf-8")

            complete_before, missing_before = manifest_status(output_dir, baseline_spec)
            self.assertFalse(complete_before)
            self.assertIn("service.yaml", missing_before)
            self.assertIn("post-deploy-evaluation-job.yaml", missing_before)

            written_files = scaffold_manifests(output_dir, build_manifest_bundle(app_root, baseline_spec))

            self.assertNotIn("deployment.yaml", written_files)
            self.assertEqual(existing_deployment.read_text(encoding="utf-8"), "existing deployment")

            complete_after, missing_after = manifest_status(output_dir, baseline_spec)
            self.assertTrue(complete_after)
            self.assertEqual(missing_after, [])

            ingress = yaml.safe_load((output_dir / "ingress.yaml").read_text(encoding="utf-8"))
            self.assertEqual(ingress["spec"]["rules"][0]["host"], "invoice-workflow-service.local")
            post_deploy_job = yaml.safe_load(
                (output_dir / "post-deploy-evaluation-job.yaml").read_text(encoding="utf-8")
            )
            with mock.patch("devops.agent.generate_gitops.ARGOCD_APPLICATIONS_DIR", Path(tmpdir) / "devops" / "k8s" / "argocd"):
                argocd_application_path = scaffold_argocd_application(
                    "invoice-workflow-service",
                    "devops-ssd-assignment",
                )
                argocd_application = yaml.safe_load(argocd_application_path.read_text(encoding="utf-8"))
            self.assertEqual(
                post_deploy_job["metadata"]["annotations"]["argocd.argoproj.io/hook"],
                "PostSync",
            )
            self.assertEqual(argocd_application["kind"], "Application")
            self.assertEqual(argocd_application["metadata"]["name"], "invoice-workflow-service")
            self.assertEqual(
                argocd_application["spec"]["source"]["path"],
                "devops/k8s/invoice-workflow-service",
            )
            self.assertEqual(post_deploy_job["metadata"]["namespace"], "argocd")
            token_env = next(
                env
                for env in post_deploy_job["spec"]["template"]["spec"]["containers"][0]["env"]
                if env["name"] == "GITHUB_TOKEN"
            )
            self.assertEqual(token_env["valueFrom"]["secretKeyRef"]["name"], "gha-post-deployment-trigger")
            self.assertEqual(token_env["valueFrom"]["secretKeyRef"]["key"], "pat")
            workflow_ref_env = next(
                env
                for env in post_deploy_job["spec"]["template"]["spec"]["containers"][0]["env"]
                if env["name"] == "OBSERVABILITY_WORKFLOW_REF"
            )
            self.assertEqual(workflow_ref_env["value"], "feat/post-deployment")
            prometheus_env = next(
                env
                for env in post_deploy_job["spec"]["template"]["spec"]["containers"][0]["env"]
                if env["name"] == "PROMETHEUS_URL"
            )
            self.assertEqual(
                prometheus_env["valueFrom"]["configMapKeyRef"]["name"],
                "post-deployment-evaluation-env",
            )
            self.assertEqual(
                prometheus_env["valueFrom"]["configMapKeyRef"]["key"],
                "PROMETHEUS_URL",
            )
            loki_env = next(
                env
                for env in post_deploy_job["spec"]["template"]["spec"]["containers"][0]["env"]
                if env["name"] == "LOKI_URL"
            )
            self.assertEqual(
                loki_env["valueFrom"]["configMapKeyRef"]["name"],
                "post-deployment-evaluation-env",
            )
            self.assertEqual(
                loki_env["valueFrom"]["configMapKeyRef"]["key"],
                "LOKI_URL",
            )
            dispatch_script = post_deploy_job["spec"]["template"]["spec"]["containers"][0]["args"][0]
            self.assertIn('Authorization: Bearer ${GITHUB_TOKEN}', dispatch_script)
            self.assertIn('"ref": "${OBSERVABILITY_WORKFLOW_REF}"', dispatch_script)
            self.assertIn('"prometheus_url": "${PROMETHEUS_URL}"', dispatch_script)
            self.assertIn('"loki_url": "${LOKI_URL}"', dispatch_script)
            self.assertIn('"update_healthy_state": "true"', dispatch_script)

    def test_ingress_can_be_disabled(self):
        baseline_spec = {
            "service": "expense-workflow-service",
            "workspace": {"path": "applications/expense-workflow-service"},
            "deployment": {
                "k8s": {
                    "namespace": "devops-ssd-assignment",
                    "deployment": {
                        "name": "expense-workflow-service",
                        "replicas": 1,
                        "container_port": 8000,
                    },
                    "service": {
                        "name": "expense-workflow-service",
                        "port": 80,
                        "target_port": 8000,
                    },
                    "ingress": {
                        "enabled": False,
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            app_root = Path(tmpdir) / "applications" / "expense-workflow-service"
            output_dir = Path(tmpdir) / "devops" / "k8s" / "expense-workflow-service"

            manifest_bundle = build_manifest_bundle(app_root, baseline_spec)
            self.assertNotIn("ingress.yaml", manifest_bundle)
            self.assertEqual(
                required_manifest_files(baseline_spec),
                [
                    "namespace.yaml",
                    "deployment.yaml",
                    "service.yaml",
                    "image-tag.yaml",
                    "post-deploy-evaluation-job.yaml",
                ],
            )

            written_files = scaffold_manifests(output_dir, manifest_bundle)
            self.assertNotIn("ingress.yaml", written_files)

            complete, missing = manifest_status(output_dir, baseline_spec)
            self.assertTrue(complete)
            self.assertEqual(missing, [])
            self.assertFalse((output_dir / "ingress.yaml").exists())


if __name__ == "__main__":
    unittest.main()
