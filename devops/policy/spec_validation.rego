package policy.spec_validation

default allow = false

required_fields = [
  "schema_version",
  "change_id",
  "service",
  "workflow_change",
  "deployment",
  "quality",
]

missing[field] {
  field := required_fields[_]
  not input.spec[field]
}

deny[msg] {
  field := missing[_]
  msg := sprintf("missing required field: %s", [field])
}

deny[msg] {
  input.spec.schema_version != "1.0.0"
  msg := sprintf("unsupported schema_version: %v", [input.spec.schema_version])
}

deny[msg] {
  not input.spec.workflow_change.baseline_stages
  msg := "workflow_change.baseline_stages is required"
}

deny[msg] {
  count(input.spec.workflow_change.baseline_stages) == 0
  msg := "workflow_change.baseline_stages must not be empty"
}

deny[msg] {
  not input.spec.quality.unit_tests
  msg := "quality.unit_tests is required"
}

deny[msg] {
  input.spec.quality.unit_tests.required != true
  msg := "quality.unit_tests.required must be true"
}

deny[msg] {
  not input.spec.quality.unit_tests.min_new_tests
  msg := "quality.unit_tests.min_new_tests is required"
}

deny[msg] {
  input.spec.quality.unit_tests.min_new_tests < 1
  msg := "quality.unit_tests.min_new_tests must be >= 1"
}

allow {
  count(deny) == 0
}
