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

Prompt reference:
- `prompts/reference.txt`

Notes:
- In `ollama` mode, contract module generation uses Ollama with strict constant validation.
- Full app source and matching GitOps manifests are generated from spec within the target app scope.
- The feat-branch workflow validates specs first, then runs deterministic generation and uploads the generated outputs as CI artifacts.
- Runtime prompts are assembled directly in `generate_code.py`; the prompt file is kept only as a reference for the next rebuild.
