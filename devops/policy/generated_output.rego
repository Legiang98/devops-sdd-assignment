package policy.generated_output

import future.keywords.contains
import future.keywords.if

default allow = false

has_generated_route(method, path) if {
  some actual in input.generated.app_routes
  actual.method == method
  actual.path == path
}

has_generated_reject_route if {
  some actual in input.generated.app_routes
  actual.method == "POST"
  endswith(actual.path, "/reject")
}

reject_expected if {
  some endpoint in input.spec.api_contract.endpoints
  upper(endpoint.method) == "POST"
  endswith(endpoint.path, "/reject")
}

deny contains msg if {
  input.generated.contract.schema_version != input.spec.schema_version
  msg := "generated contract SCHEMA_VERSION mismatch"
}

deny contains msg if {
  input.generated.contract.change_id != input.spec.change_id
  msg := "generated contract CHANGE_ID mismatch"
}

deny contains msg if {
  input.generated.contract.service != input.spec.service
  msg := "generated contract SERVICE mismatch"
}

deny contains msg if {
  baseline := [s.name | s := input.spec.workflow_change.baseline_stages[_]]
  input.generated.contract.baseline_stages != baseline
  msg := "generated contract BASELINE_STAGES mismatch"
}

deny contains msg if {
  input.spec.workflow_change.new_stage
  input.generated.contract.new_stage_name != input.spec.workflow_change.new_stage.name
  msg := "generated contract NEW_STAGE_NAME mismatch"
}

deny contains msg if {
  input.spec.workflow_change.new_stage
  input.generated.contract.new_stage_threshold != input.spec.workflow_change.new_stage.required_when.amount_gte
  msg := "generated contract NEW_STAGE_THRESHOLD mismatch"
}

deny contains msg if {
  not input.spec.workflow_change.new_stage
  input.generated.contract.new_stage_name != null
  msg := "generated contract NEW_STAGE_NAME mismatch"
}

deny contains msg if {
  not input.spec.workflow_change.new_stage
  input.generated.contract.new_stage_threshold != null
  msg := "generated contract NEW_STAGE_THRESHOLD mismatch"
}

deny contains msg if {
  not has_generated_route("GET", "/health")
  msg := "generated app missing route GET /health"
}

deny contains msg if {
  not has_generated_route("GET", "/metrics")
  msg := "generated app missing route GET /metrics"
}

deny contains msg if {
  some endpoint in input.spec.api_contract.endpoints
  method := upper(endpoint.method)
  path := endpoint.path
  not has_generated_route(method, path)
  msg := sprintf("generated app missing route %s %s", [method, path])
}

deny contains msg if {
  reject_expected
  not has_generated_reject_route
  msg := "generated app reject route does not match spec"
}

deny contains msg if {
  not reject_expected
  has_generated_reject_route
  msg := "generated app reject route does not match spec"
}

allow if {
  count(deny) == 0
}
