#!/usr/bin/env bash
# Serve a local GGUF model with llama-server (OpenAI-compatible API) for --agent llm.
# Every parameter is listed below with its default; override any of them on the command line, e.g.
#   scripts/serve_llm.sh --ctx-size 131072 --port 8081
# Sampling (temperature, top_p, ...) is left to the model's recommended defaults stored in the GGUF;
# main.py records the values the server reports in params.json.
set -euo pipefail

# --- model ---
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/ondemand/llama.cpp/build/bin/llama-server}"
MODEL="${MODEL:-$HOME/ondemand/models/Nemotron-3-Nano-30B-A3B-Q8_0.gguf}"
ALIAS="${ALIAS:-nemotron-3-nano-30b-a3b-q8}"   # use the same name as --llm-name

# --- hardware ---
GPUS="${GPUS:-0,1}"         # the model is split by layers across these GPUs
CTX_SIZE="262144"           # total context in tokens, shared by all slots
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
  --host "$HOST" --port "$PORT" \
  "$@"
