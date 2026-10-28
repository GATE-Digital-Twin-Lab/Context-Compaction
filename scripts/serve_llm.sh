#!/usr/bin/env bash
# Serve a local GGUF model with llama-server (OpenAI-compatible API) for --agent llm.
# Usage: scripts/serve_llm.sh [PRESET] [extra llama-server options]
#   scripts/serve_llm.sh                          # qwen3.8-27b (default)
#   scripts/serve_llm.sh nemotron-3-nano --port 8081
# A preset sets the model file, its alias (pass the same name as --llm-name) and the model's
# recommended sampling, which becomes the server default; main.py records what the server
# reports in params.json. Extra options come last, so they override the preset.
set -euo pipefail

PRESET="${1:-qwen3.8-27b}"
[[ $# -gt 0 ]] && shift
MODELS="${MODELS:-$HOME/ondemand/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/ondemand/llama.cpp/build/bin/llama-server}"

case "$PRESET" in
  qwen3.8-27b)
    # Model card, thinking mode: temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence_penalty 0,
    # repetition_penalty 1.0. Same architecture as Qwen3.6 (3 Gated DeltaNet : 1 attention layer).
    MODEL="$MODELS/Qwen3.8-27B-Q8_0.gguf"
    ALIAS="qwen3.8-27b-q8"
    CTX_SIZE="262144"   # native maximum; the KV cache is ~64 KB per token
    SAMPLING=(--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 0 --repeat-penalty 1.0)
    ;;
  qwen3.6-27b)
    # Model card, thinking mode for general tasks: temperature 1.0, top_p 0.95, top_k 20, min_p 0,
    # presence_penalty 0, repetition_penalty 1.0; output length 32,768 tokens.
    MODEL="$MODELS/Qwen3.6-27B-Q8_0.gguf"
    ALIAS="qwen3.6-27b-q8"
    CTX_SIZE="262144"   # the model's maximum; hybrid attention keeps the KV cache at ~64 KB per token
    SAMPLING=(--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 0 --repeat-penalty 1.0)
    ;;
  nemotron-3-nano)
    # Model card and GGUF metadata: temperature 1.0, top_p 1.0 (no top_k / min_p truncation).
    MODEL="$MODELS/Nemotron-3-Nano-30B-A3B-Q8_0.gguf"
    ALIAS="nemotron-3-nano-30b-a3b-q8"
    CTX_SIZE="262144"
    SAMPLING=(--temp 1.0 --top-p 1.0 --top-k 0 --min-p 0)
    ;;
  *)
    echo "Unknown preset '$PRESET' (available: qwen3.8-27b, qwen3.6-27b, nemotron-3-nano)." >&2
    exit 1
    ;;
esac

# --- hardware ---
GPUS="${GPUS:-0,1}"         # the model is split by layers across these GPUs
PARALLEL="1"                # slots (concurrent episodes); each gets CTX_SIZE / PARALLEL tokens

# --- network ---
HOST="127.0.0.1"
PORT="8080"

# Context shift stays off: the server must never drop old tokens on its own, which would be an
# uncontrolled compaction. A full context is reported as an error and ends the episode instead.
CUDA_VISIBLE_DEVICES="$GPUS" exec "$LLAMA_SERVER" \
  --model "$MODEL" --alias "$ALIAS" \
  --ctx-size "$CTX_SIZE" --parallel "$PARALLEL" \
  --n-gpu-layers 999 --split-mode layer --flash-attn on \
  --jinja --reasoning-format deepseek --no-context-shift \
  "${SAMPLING[@]}" \
  --host "$HOST" --port "$PORT" \
  "$@"
