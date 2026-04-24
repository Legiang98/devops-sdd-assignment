package policy.spec_validation

import future.keywords.contains
import future.keywords.if

default allow = false

required_fields = [
  "schema_version",
  "change_id",
  "service",
  "workflow_change",
  "deployment",
  "docs",
  "quality",
]

missing contains field if {
  field := required_fields[_]
  not input.spec[field]
}

deny contains msg if {
  field := missing[_]
  msg := sprintf("missing required field: %s", [field])
}

deny contains msg if {
  input.spec.schema_version != "1.0.0"
  msg := sprintf("unsupported schema_version: %v", [input.spec.schema_version])
}

deny contains msg if {
  not input.spec.workflow_change.baseline_stages
  msg := "workflow_change.baseline_stages is required"
}

deny contains msg if {
  count(input.spec.workflow_change.baseline_stages) == 0
  msg := "workflow_change.baseline_stages must not be empty"
}

deny contains msg if {
  not input.spec.quality.unit_tests
  msg := "quality.unit_tests is required"
}

deny contains msg if {
  not input.spec.docs.swagger
  msg := "docs.swagger is required"
}

deny contains msg if {
  not input.spec.docs.swagger.path
  not input.spec.docs.swagger.url
  msg := "docs.swagger.path or docs.swagger.url is required"
}

deny contains msg if {
  input.spec.quality.unit_tests.required != true
  msg := "quality.unit_tests.required must be true"
}

deny contains msg if {
  not input.spec.quality.unit_tests.min_new_tests
  msg := "quality.unit_tests.min_new_tests is required"
}

deny contains msg if {
  input.spec.quality.unit_tests.min_new_tests < 1
  msg := "quality.unit_tests.min_new_tests must be >= 1"
}

allow if {
  count(deny) == 0
}
