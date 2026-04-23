# GitHub Environment Terraform (Hardcoded Repo Config)

This module manages a GitHub Actions environment for this repository.

Hardcoded in `main.tf`:
- owner: `lesip`
- repository: `devops-ssd-assignment`
- environment: `poc`
- variables:
  - `DEFAULT_SPEC_FILE`
  - `PYTHON_VERSION`

## Required input

- `github_token` (sensitive)

## Optional input

- `environment_secrets` map (sensitive)

## Usage

```bash
cd devops/infra
export TF_VAR_github_token='<your_github_token>'
terraform init
terraform plan
terraform apply
```

Optional secrets example:

```bash
export TF_VAR_environment_secrets='{"SONAR_TOKEN":"xxxxx"}'
```
