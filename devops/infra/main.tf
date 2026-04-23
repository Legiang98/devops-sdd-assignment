locals {
  github_owner     = "lesip"
  repository_name  = "devops-ssd-assignment"
  environment_name = "poc"
  environment_variables = {
    DEFAULT_SPEC_FILE = "applications/expense-workflow-service/specs/EXPENSE-finance-approval.yaml"
    PYTHON_VERSION    = "3.12"
  }
}

provider "github" {
  owner = local.github_owner
  token = var.github_token
}

resource "github_repository_environment" "this" {
  repository  = local.repository_name
  environment = local.environment_name
}

resource "github_actions_environment_variable" "this" {
  for_each = local.environment_variables

  repository    = local.repository_name
  environment   = github_repository_environment.this.environment
  variable_name = each.key
  value         = each.value
}

resource "github_actions_environment_secret" "this" {
  for_each = var.environment_secrets

  repository      = local.repository_name
  environment     = github_repository_environment.this.environment
  secret_name     = each.key
  plaintext_value = each.value
}
