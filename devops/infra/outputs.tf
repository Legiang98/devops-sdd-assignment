output "environment_name" {
  description = "Created GitHub Actions environment name"
  value       = github_repository_environment.this.environment
}

output "environment_variables" {
  description = "Environment variable names created"
  value       = keys(github_actions_environment_variable.this)
}

output "environment_secrets" {
  description = "Environment secret names created"
  value       = keys(github_actions_environment_secret.this)
}
