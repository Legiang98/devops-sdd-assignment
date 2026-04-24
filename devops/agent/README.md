# Agent

Scripted workflow that reads spec input and generates:
- release artifacts (`rules.json`, `deploy_manifest.json`, evidence)
- generated source contract (`src/generated/spec_contract.py`)
- generated service module (`src/main.py`)

Codegen provider options:
- `deterministic` (default)
- `ollama` via env:
  - `AGENT_CODEGEN_PROVIDER=ollama`
  - `OLLAMA_MODEL=qwen2.5:7b`
  - `OLLAMA_BASE_URL=http://127.0.0.1:11434`

Prompt files for Ollama codegen:
- `prompts/codegen_system.txt`
- `prompts/codegen_user_template.txt`

Notes:
- In `ollama` mode, contract module generation uses Ollama with strict constant validation.
- Service module generation uses a deterministic template derived from spec contract.
