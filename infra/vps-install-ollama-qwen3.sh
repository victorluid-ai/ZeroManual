#!/usr/bin/env bash
# Run this ON THE VPS via SSH (not from this machine — no remote exec available).
# Installs Ollama + Qwen3 8B for the n8n review-reply/social-post workflows.
set -euo pipefail

echo "== Before =="
free -h
df -h /

echo "== Installing Ollama =="
curl -fsSL https://ollama.com/install.sh | sh

echo "== Pulling qwen3:8b =="
ollama pull qwen3:8b

echo "== Sanity check =="
ollama run qwen3:8b "Responde en una frase: ¿qué eres?" --verbose=false

echo "== API check =="
curl -s http://localhost:11434/api/tags

echo "== After =="
free -h
df -h /

cat <<'EOF'

Next (manual, in n8n UI):
  1. Open the review-reply / social-post workflow.
  2. Point the AI node at: http://localhost:11434/v1/chat/completions (OpenAI-compatible)
  3. Model: qwen3:8b
  4. System prompt: Spain Spanish, avoid "ustedes"/"computadora", add few-shot brand-tone examples.
  5. Keep the existing human-approval step — track edit-rate for 1-2 weeks before trusting drafts fully.
EOF
