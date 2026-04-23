# Agent

Scripted workflow that reads spec input and generates:
- release artifacts (`rules.json`, `deploy_manifest.json`, evidence)
- deterministic source contract (`src/generated/spec_contract.py`)

Codegen provider options:
- `deterministic` (default)
- `ollama` via env:
  - `AGENT_CODEGEN_PROVIDER=ollama`
  - `OLLAMA_MODEL=qwen2.5:7b`
  - `OLLAMA_BASE_URL=http://127.0.0.1:11434`
