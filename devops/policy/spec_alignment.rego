package policy.spec_alignment

default allow = false

workspace_path := object.get(input.spec, "workspace", {}).path
manifest_path := object.get(input.spec, "workspace", {}).manifest_path
argocd_cfg := object.get(object.get(input.spec, "gitops", {}), "argocd", {})
argocd_enabled := object.get(argocd_cfg, "enabled", true)
argocd_application_name := object.get(argocd_cfg, "application_name", "")
default_argocd_application_name := object.get(split(manifest_path, "/"), count(split(manifest_path, "/")) - 1, "")
effective_argocd_application_name := object.get(argocd_cfg, "application_name", default_argocd_application_name)

has_generated_route(method, path) if {
  some actual in input.generated.codegen_report.app_routes
  actual.method == method
  actual.path == path
}

reject_expected if {
  some endpoint in input.spec.api_contract.endpoints
  upper(endpoint.method) == "POST"
  endpoint.path == "/expenses/{expense_id}/reject"
}

deny[msg] {
  input.generated.rules.release_id != input.spec.change_id
  msg := "rules.release_id must match spec.change_id"
}

deny[msg] {
  input.generated.deploy_manifest.release_id != input.spec.change_id
  msg := "deploy_manifest.release_id must match spec.change_id"
}

deny[msg] {
  input.generated.codegen_report.release_id != input.spec.change_id
  msg := "codegen_report.release_id must match spec.change_id"
}

deny[msg] {
  workspace_path != ""
  input.generated.codegen_report.app_path != workspace_path
  msg := "codegen_report.app_path must match spec.workspace.path"
}

deny[msg] {
  manifest_path != ""
  input.generated.codegen_report.gitops_path != manifest_path
  msg := "codegen_report.gitops_path must match spec.workspace.manifest_path"
}

deny[msg] {
  input.generated.codegen_report.constants.schema_version != input.spec.schema_version
  msg := "generated code SCHEMA_VERSION mismatch"
}

deny[msg] {
  input.generated.codegen_report.constants.change_id != input.spec.change_id
  msg := "generated code CHANGE_ID mismatch"
}

deny[msg] {
  input.generated.codegen_report.constants.service != input.spec.service
  msg := "generated code SERVICE mismatch"
}

deny[msg] {
  baseline := [s.name | s := input.spec.workflow_change.baseline_stages[_]]
  input.generated.codegen_report.constants.baseline_stage_names != baseline
  msg := "generated code BASELINE_STAGES mismatch"
}

deny[msg] {
  input.spec.workflow_change.new_stage
  input.generated.codegen_report.constants.new_stage_name != input.spec.workflow_change.new_stage.name
  msg := "generated code NEW_STAGE_NAME mismatch"
}

deny[msg] {
  input.spec.workflow_change.new_stage
  input.generated.codegen_report.constants.new_stage_threshold != input.spec.workflow_change.new_stage.required_when.amount_gte
  msg := "generated code NEW_STAGE_THRESHOLD mismatch"
}

deny[msg] {
  not input.spec.workflow_change.new_stage
  input.generated.codegen_report.constants.new_stage_name != null
  msg := "generated code NEW_STAGE_NAME mismatch"
}

deny[msg] {
  not input.spec.workflow_change.new_stage
  input.generated.codegen_report.constants.new_stage_threshold != null
  msg := "generated code NEW_STAGE_THRESHOLD mismatch"
}

deny[msg] {
  some endpoint in input.spec.api_contract.endpoints
  method := upper(endpoint.method)
  path := endpoint.path
  not has_generated_route(method, path)
  msg := sprintf("generated app missing route %s %s", [method, path])
}

deny[msg] {
  not has_generated_route("GET", "/health")
  msg := "generated app missing route GET /health"
}

deny[msg] {
  not has_generated_route("GET", "/metrics")
  msg := "generated app missing route GET /metrics"
}

deny[msg] {
  some actual in input.generated.codegen_report.app_routes
  not actual.path == "/health"
  not actual.path == "/metrics"
  not some expected in input.spec.api_contract.endpoints
  upper(expected.method) == actual.method
  expected.path == actual.path
  msg := sprintf("generated app has unexpected route %s %s", [actual.method, actual.path])
}

deny[msg] {
  reject_expected
  not has_generated_route("POST", "/expenses/{expense_id}/reject")
  msg := "generated app reject route does not match spec"
}

deny[msg] {
  not reject_expected
  has_generated_route("POST", "/expenses/{expense_id}/reject")
  msg := "generated app reject route does not match spec"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.namespace.name != input.spec.deployment.k8s.namespace
  msg := "namespace manifest name mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.deployment.name != input.spec.deployment.k8s.deployment.name
  msg := "deployment manifest name mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.deployment.namespace != input.spec.deployment.k8s.namespace
  msg := "deployment manifest namespace mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.deployment.replicas != input.spec.deployment.k8s.deployment.replicas
  msg := "deployment replicas mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.deployment.container_port != input.spec.deployment.k8s.deployment.container_port
  msg := "deployment container_port mismatch"
}

deny[msg] {
  not input.generated.codegen_report.manifest_summary.deployment.image
  msg := "deployment image is required"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.service.name != input.spec.deployment.k8s.service.name
  msg := "service manifest name mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.service.namespace != input.spec.deployment.k8s.namespace
  msg := "service manifest namespace mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.service.port != input.spec.deployment.k8s.service.port
  msg := "service port mismatch"
}

deny[msg] {
  input.generated.codegen_report.manifest_summary.service.target_port != input.spec.deployment.k8s.service.target_port
  msg := "service targetPort mismatch"
}

deny[msg] {
  input.spec.deployment.k8s.ingress.enabled
  not input.generated.codegen_report.manifest_summary.ingress.enabled
  msg := "ingress manifest must be enabled when spec ingress.enabled is true"
}

deny[msg] {
  input.spec.deployment.k8s.ingress.enabled
  input.generated.codegen_report.manifest_summary.ingress.kind != "Ingress"
  msg := "ingress manifest must be a Kubernetes Ingress when enabled"
}

deny[msg] {
  input.spec.deployment.k8s.ingress.enabled
  input.generated.codegen_report.manifest_summary.ingress.backend_service != input.spec.deployment.k8s.service.name
  msg := "ingress backend service mismatch"
}

deny[msg] {
  not input.spec.deployment.k8s.ingress.enabled
  input.generated.codegen_report.manifest_summary.ingress.enabled
  msg := "ingress manifest must stay disabled when spec ingress.enabled is false"
}

deny[msg] {
  argocd_enabled
  not input.generated.codegen_report.argocd_application
  msg := "Argo CD application manifest is required"
}

deny[msg] {
  argocd_enabled
  input.generated.codegen_report.argocd_application.name != effective_argocd_application_name
  msg := "Argo CD application metadata.name mismatch"
}

deny[msg] {
  argocd_enabled
  input.generated.codegen_report.argocd_application.namespace != "argocd"
  msg := "Argo CD application namespace must be argocd"
}

deny[msg] {
  argocd_enabled
  manifest_path != ""
  input.generated.codegen_report.argocd_application.source_path != manifest_path
  msg := "Argo CD application source.path must match spec.workspace.manifest_path"
}

deny[msg] {
  argocd_enabled
  input.generated.codegen_report.argocd_application.destination_namespace != input.spec.deployment.k8s.namespace
  msg := "Argo CD application destination namespace mismatch"
}

deny[msg] {
  not argocd_enabled
  input.generated.codegen_report.argocd_application
  msg := "Argo CD application must not be generated when spec disables it"
}

deny[msg] {
  not input.spec.workflow_change.new_stage
  count(input.generated.rules.workflow.stages) != count(input.spec.workflow_change.baseline_stages)
  msg := "workflow stage count mismatch"
}

deny[msg] {
  input.spec.workflow_change.new_stage
  count(input.generated.rules.workflow.stages) != count(input.spec.workflow_change.baseline_stages) + 1
  msg := "workflow stage count mismatch"
}

deny[msg] {
  some i
  expected := input.spec.workflow_change.baseline_stages[i]
  actual := input.generated.rules.workflow.stages[i]
  expected.name != actual.name
  msg := sprintf("stage[%d] name mismatch", [i])
}

deny[msg] {
  some i
  expected := input.spec.workflow_change.baseline_stages[i]
  actual := input.generated.rules.workflow.stages[i]
  expected.required_when.amount_gte != actual.required_when.amount_gte
  msg := sprintf(
    "stage[%d] threshold mismatch: expected %v, got %v",
    [i, expected.required_when.amount_gte, actual.required_when.amount_gte],
  )
}

deny[msg] {
  input.spec.workflow_change.new_stage
  base_count := count(input.spec.workflow_change.baseline_stages)
  expected := input.spec.workflow_change.new_stage
  actual := input.generated.rules.workflow.stages[base_count]
  expected.name != actual.name
  msg := sprintf("stage[%d] name mismatch", [base_count])
}

deny[msg] {
  input.spec.workflow_change.new_stage
  base_count := count(input.spec.workflow_change.baseline_stages)
  expected := input.spec.workflow_change.new_stage
  actual := input.generated.rules.workflow.stages[base_count]
  expected.required_when.amount_gte != actual.required_when.amount_gte
  msg := sprintf(
    "stage[%d] threshold mismatch: expected %v, got %v",
    [base_count, expected.required_when.amount_gte, actual.required_when.amount_gte],
  )
}

allow {
  count(deny) == 0
}
