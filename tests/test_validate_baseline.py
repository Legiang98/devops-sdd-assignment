import tempfile
import unittest
from pathlib import Path

from devops.policy.validate_baseline import find_baseline, validate_baseline


class ValidateBaselineTests(unittest.TestCase):
    def test_validate_baseline_accepts_explicit_workspace_and_optional_ingress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_root = Path(tmpdir) / "applications" / "sample-service"
            (app_root / "specs").mkdir(parents=True)
            baseline_path = app_root / "specs" / "BASELINE.yaml"
            baseline_path.write_text("schema_version: 1.0.0\n", encoding="utf-8")

            baseline = {
                "schema_version": "1.0.0",
                "change_id": "BASELINE",
                "service": "sample-service",
                "workflow_change": {
                    "baseline_stages": [{"name": "system", "required_when": {"amount_gte": 0}}],
                },
                "workspace": {
                    "path": "applications/sample-service",
                    "src_path": "src",
                    "tests_path": "tests",
                    "dockerfile_path": "Dockerfile",
                    "manifest_path": "devops/k8s/sample-service",
                },
                "docs": {"swagger": {"path": "/openapi.json"}},
                "deployment": {
                    "k8s": {
                        "namespace": "devops-ssd-assignment",
                        "deployment": {"name": "sample-service", "replicas": 1, "container_port": 8000},
                        "service": {"name": "sample-service", "port": 80, "target_port": 8000},
                        "ingress": {"enabled": False},
                    }
                },
                "quality": {
                    "unit_tests": {"required": True, "min_new_tests": 1},
                },
            }

            self.assertEqual(find_baseline(app_root), baseline_path)
            self.assertEqual(validate_baseline(baseline, baseline_path, app_root), [])

    def test_validate_baseline_rejects_invalid_workspace_and_ingress_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_root = Path(tmpdir) / "applications" / "sample-service"
            baseline_path = app_root / "specs" / "BASELINE.yaml"
            baseline = {
                "schema_version": "1.0.0",
                "change_id": "BASELINE",
                "service": "sample-service",
                "workflow_change": {
                    "baseline_stages": [{"name": "system", "required_when": {"amount_gte": 0}}],
                },
                "workspace": {
                    "path": "applications/wrong-service",
                    "src_path": "app",
                    "tests_path": "specs",
                    "dockerfile_path": "Dockerfile.dev",
                    "manifest_path": "devops/k8s/wrong-service",
                },
                "docs": {"swagger": {"path": "/openapi.json"}},
                "deployment": {
                    "k8s": {
                        "namespace": "devops-ssd-assignment",
                        "deployment": {"name": "sample-service", "replicas": 0, "container_port": 0},
                        "service": {"name": "sample-service", "port": 0, "target_port": 0},
                        "ingress": {"enabled": "false"},
                    }
                },
                "quality": {
                    "unit_tests": {"required": True, "min_new_tests": 1},
                },
            }

            violations = validate_baseline(baseline, baseline_path, app_root)
            self.assertIn("workspace.path must be applications/sample-service", violations)
            self.assertIn("workspace.src_path must be src", violations)
            self.assertIn("workspace.manifest_path must be devops/k8s/sample-service", violations)
            self.assertIn("deployment.k8s.deployment.replicas must be an integer >= 1", violations)
            self.assertIn("deployment.k8s.ingress.enabled must be a boolean when present", violations)


if __name__ == "__main__":
    unittest.main()
