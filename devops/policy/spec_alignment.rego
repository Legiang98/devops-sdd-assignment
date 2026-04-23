package policy.spec_alignment

default allow = false

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
