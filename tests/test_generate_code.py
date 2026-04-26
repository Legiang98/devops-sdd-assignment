import unittest

from devops.agent.generate_code import (
    dockerfile_body,
    expected_contract,
    generic_app_module_body,
    validate_app_source_against_spec,
)


class GenerateCodeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
