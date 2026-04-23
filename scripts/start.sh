#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[start] Bootstrapping local PoC environment"

if [ ! -d .venv ]; then
  echo "[start] Creating virtualenv (.venv)"
  python -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt >/dev/null

echo "[start] Checking Minikube"
if command -v minikube >/dev/null 2>&1; then
  minikube status >/dev/null 2>&1 || minikube start
else
  echo "[start] minikube not found. Install it or start your local cluster manually."
fi

echo "[start] Checking local LLM runtime (Ollama example)"
if command -v ollama >/dev/null 2>&1; then
  echo "[start] ollama detected"
else
  echo "[start] ollama not found. Start your preferred local LLM runtime manually."
fi

echo "[start] Done"
