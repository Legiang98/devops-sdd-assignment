variable "github_token" {
  description = "GitHub token with permission to manage repository environments/variables/secrets"
  type        = string
  sensitive   = true
}

variable "environment_secrets" {
  description = "Sensitive GitHub Actions environment secrets"
  type        = map(string)
  sensitive   = true
  default     = {}
}
