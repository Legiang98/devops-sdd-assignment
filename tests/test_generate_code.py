import unittest

from devops.agent.generate_code import (
    dockerfile_body,
    expected_contract,
    generic_app_module_body,
    requirements_body,
    validate_app_source_against_spec,
)


class GenerateCodeTests(unittest.TestCase):
    def test_generic_app_includes_probe_alias_routes(self):
        spec = {
            "schema_version": "1.0.0",
            "change_id": "PURCHASE-BASELINE",
            "service": "purchase-request-workflow-service",
            "workflow_change": {
                "baseline_stages": [{"name": "requester", "required_when": {"amount_gte": 0}}],
            },
            "api_contract": {
                "endpoints": [
                    {"method": "POST", "path": "/purchase-requests"},
                ]
            },
        }

        contract = expected_contract(spec)
        app_source = generic_app_module_body(contract, "Purchase Request Workflow Service")

        self.assertIn('@app.get("/health")', app_source)
        self.assertIn('@app.get("/healthz")', app_source)
        self.assertIn('@app.get("/readiness")', app_source)
        self.assertEqual(validate_app_source_against_spec(app_source, spec), [])

    def test_generic_app_validates_against_dynamic_purchase_request_routes(self):
        spec = {
            "schema_version": "1.0.0",
            "change_id": "PURCHASE-MANAGER-APPROVAL",
            "service": "purchase-request-workflow-service",
            "workflow_change": {
                "baseline_stages": [{"name": "requester", "required_when": {"amount_gte": 0}}],
                "new_stage": {"name": "manager", "required_when": {"amount_gte": 1000}},
            },
            "api_contract": {
                "endpoints": [
                    {"method": "POST", "path": "/purchase-requests"},
                    {"method": "GET", "path": "/purchase-requests/{request_id}"},
                    {"method": "POST", "path": "/purchase-requests/{request_id}/approve"},
                ]
            },
        }

        contract = expected_contract(spec)
        app_source = generic_app_module_body(contract, "Purchase Request Workflow Service")

        self.assertEqual(validate_app_source_against_spec(app_source, spec), [])

    def test_reject_flag_is_dynamic_for_non_expense_route_family(self):
        spec = {
            "schema_version": "1.0.0",
            "change_id": "PURCHASE-REJECT",
            "service": "purchase-request-workflow-service",
            "workflow_change": {
                "baseline_stages": [{"name": "requester", "required_when": {"amount_gte": 0}}],
            },
            "api_contract": {
                "endpoints": [
                    {"method": "POST", "path": "/purchase-requests/{request_id}/reject"},
                ]
            },
        }

        contract = expected_contract(spec)

        self.assertTrue(contract["reject_endpoint_enabled"])

    def test_dockerfile_uses_repo_root_relative_requirements_path(self):
        dockerfile = dockerfile_body("purchase-request-workflow-service")

        self.assertIn(
            "COPY applications/purchase-request-workflow-service/requirements.txt /app/requirements.txt",
            dockerfile,
        )
        self.assertNotIn("COPY requirements.txt /app/requirements.txt", dockerfile)

    def test_requirements_include_observability_dependencies_when_imported(self):
        src_files = {
            "main.py": """
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from pydantic import BaseModel
from prometheus_client import Counter
"""
        }

        requirements = requirements_body(src_files)

        self.assertIn("fastapi>=0.116.0", requirements)
        self.assertIn("uvicorn>=0.35.0", requirements)
        self.assertIn("pydantic>=2.11.0", requirements)
        self.assertIn("prometheus-client>=0.22.1", requirements)
        self.assertIn("opentelemetry-api>=1.27.0", requirements)
        self.assertIn("opentelemetry-sdk>=1.27.0", requirements)
        self.assertIn("opentelemetry-instrumentation-fastapi>=0.48b0", requirements)
        self.assertIn("opentelemetry-exporter-otlp-proto-http>=1.27.0", requirements)


if __name__ == "__main__":
    unittest.main()
