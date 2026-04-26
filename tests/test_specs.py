import tempfile
import unittest
from pathlib import Path

from devops.spec.specs import load_resolved_spec


class SpecLoadingTests(unittest.TestCase):
    def test_load_resolved_spec_merges_named_baseline_variant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_root = Path(tmpdir) / "applications" / "invoice-workflow-service"
            specs_dir = app_root / "specs"
            specs_dir.mkdir(parents=True)

            (specs_dir / "INV-BASELINE.yaml").write_text(
                "\n".join(
                    [
                        "schema_version: 1.0.0",
                        "change_id: INV-BASELINE",
                        "service: invoice-workflow-service",
                        "workflow_change:",
                        "  baseline_stages:",
                        "    - name: system",
                        "      required_when:",
                        "        amount_gte: 0",
                        "workspace:",
                        "  path: applications/invoice-workflow-service",
                        "docs:",
                        "  swagger:",
                        "    path: /openapi.json",
                        "deployment:",
                        "  k8s:",
                        "    namespace: devops-ssd-assignment",
                        "quality:",
                        "  unit_tests:",
                        "    required: true",
                        "    min_new_tests: 1",
                        "api_contract:",
                        "  endpoints:",
                        "    - method: POST",
                        "      path: /invoices",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            feature_path = specs_dir / "INVOICE-finance-approval.yaml"
            feature_path.write_text(
                "\n".join(
                    [
                        "schema_version: 1.0.0",
                        "change_id: INV-FINANCE-APPROVAL",
                        "service: invoice-workflow-service",
                        "workflow_change:",
                        "  new_stage:",
                        "    name: finance",
                        "    required_when:",
                        "      amount_gte: 5000",
                        "api_contract:",
                        "  endpoints:",
                        "    - method: POST",
                        "      path: /invoices/{invoice_id}/approve",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            resolved = load_resolved_spec(feature_path)

            self.assertEqual(resolved["workflow_change"]["baseline_stages"][0]["name"], "system")
            self.assertEqual(resolved["workflow_change"]["new_stage"]["name"], "finance")
            self.assertEqual(
                {
                    (endpoint["method"], endpoint["path"])
                    for endpoint in resolved["api_contract"]["endpoints"]
                },
                {
                    ("POST", "/invoices"),
                    ("POST", "/invoices/{invoice_id}/approve"),
                },
            )


if __name__ == "__main__":
    unittest.main()
