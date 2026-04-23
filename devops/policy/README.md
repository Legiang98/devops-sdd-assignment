# Policy Gate

Policy-as-code controls between generated artifacts and deployment.

Files:
- `spec_validation.rego`: validates spec input shape and supported schema version.
- `spec_alignment.rego`: validates generated artifacts and generated code evidence against spec.
- `check_spec_alignment.py`: validates generated release artifacts and writes `policy-report.json`.
- `check_generated_code_alignment.py`: validates generated source contract and writes `code-policy-report.json`.

Execution:
- `scripts/gate.sh` runs OPA/Rego checks when `opa` is installed.
- It always runs Python checks to produce evidence reports under `build/releases/<id>/evidence/`.
