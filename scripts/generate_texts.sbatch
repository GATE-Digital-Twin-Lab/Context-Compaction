#!/usr/bin/env bash
#SBATCH --job-name=potion-texts
#SBATCH --gres=gpu:2                 # 2x RTX 5090 (32 GB each): Qwen3.8-27B Q8 (~29 GB) + KV cache, split by layers
#SBATCH --cpus-per-task=8            # llama-server's CPU threads and the Python runner
#SBATCH --mem=64G                    # host RAM: the GGUF is memory-mapped while loading, plus headroom
#SBATCH --time=08:00:00              # about 2-3 hours per plant (44 sheets); raise it for several plants
#SBATCH --output=temp/%x-%j.out      # temp/ exists in the repo and is ignored by git
##SBATCH --partition=<name>          # set your cluster's GPU partition (remove one '#')
##SBATCH --gres=gpu:rtx5090:2        # if the cluster names GPU types, use this line instead
#
# Write the corpus texts (layer 4) with a local model: start llama-server, write and check every sheet of
# the given plants (one plant after another, each request a fresh conversation), stop the server.
#   sbatch scripts/generate_texts.sbatch mint                      # one plant (recommended: one job per plant)
#   sbatch scripts/generate_texts.sbatch mint sage                 # several, in this order
#   sbatch scripts/generate_texts.sbatch mint -- --attempts 5      # options after -- go to corpus.write
#   sbatch scripts/generate_texts.sbatch -- --sheets folk:mint:01  # single sheets
#   sbatch scripts/generate_texts.sbatch -- --trials               # the five trial ledgers only (or: -- --trials S D)
# Run one job at a time: all runs share the image registry (content/texts/registry.json), and a second
# run refuses to start while temp/corpus_write.lock exists.
# Output: one folder per source, content/texts/<kind>-<plant>-<nn>/: metadata.json (what the source implies),
# <kind>-<plant>-<nn>.txt (accepted) or failed.txt + failed.json (the last attempt and its problems),
# temp/corpus_write/<plant>.jsonl (every call), temp/potion-texts-<job>.out and temp/llama-<job>.log.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"

PRESET="${PRESET:-qwen3.8-27b}"          # a preset of scripts/serve_llm.sh
MODEL_ALIAS="${MODEL_ALIAS:-qwen3.8-27b-q8}"
CTX_SIZE="${CTX_SIZE:-65536}"            # one slot: prompt (~5k tokens) + thinking + text fits easily
JOB="${SLURM_JOB_ID:-local}"
PORT="${PORT:-$((20000 + ${SLURM_JOB_ID:-0} % 10000))}"   # per job, so jobs on one node do not collide
READY_TIMEOUT="${READY_TIMEOUT:-1200}"   # seconds to wait for the model to load

# Plants before '--', options for corpus.write after it.
PLANTS=()
while [[ $# -gt 0 && "$1" != "--" ]]; do PLANTS+=("$1"); shift; done
[[ "${1:-}" == "--" ]] && shift
EXTRA=("$@")

# Optional environment setup, e.g. VENV=$HOME/venvs/potion sbatch ...
[[ -n "${VENV:-}" ]] && source "$VENV/bin/activate"
# module load cuda   # if your cluster needs it for llama-server

mkdir -p temp
SERVER_LOG="temp/llama-$JOB.log"
echo "job $JOB on $(hostname): GPUs ${CUDA_VISIBLE_DEVICES:-unset}, port $PORT, plants: ${PLANTS[*]:-all}"

# Slurm sets CUDA_VISIBLE_DEVICES to the GPUs it gave this job; serve_llm.sh reads them from GPUS.
GPUS="${CUDA_VISIBLE_DEVICES:-0,1}" scripts/serve_llm.sh "$PRESET" \
  --port "$PORT" --ctx-size "$CTX_SIZE" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

# /health answers 503 while the model loads and 200 once it is ready.
waited=0
until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "llama-server exited during start-up; last lines of $SERVER_LOG:" >&2
    tail -n 40 "$SERVER_LOG" >&2
    exit 1
  fi
  if (( waited >= READY_TIMEOUT )); then
    echo "llama-server not ready after ${READY_TIMEOUT}s; see $SERVER_LOG" >&2
    exit 1
  fi
  sleep 10; waited=$((waited + 10))
done
echo "llama-server ready after ${waited}s"

ARGS=(--server "http://127.0.0.1:$PORT" --model "$MODEL_ALIAS")
[[ ${#PLANTS[@]} -gt 0 ]] && ARGS+=(--plants "${PLANTS[@]}")
python -m corpus.write "${ARGS[@]}" ${EXTRA[@]+"${EXTRA[@]}"}
