#!/usr/bin/env bash
# Run one Potion Garden episode.
# Every parameter is listed below with its default; override any of them on the command line, e.g.
#   scripts/run_experiment.sh --garden-size 12 --goals "time:S:30,target:I:10" --env-seed 7
set -euo pipefail
cd "$(dirname "$0")/.."

# --- agent ---
AGENT="random"            # llm | random | oracle
LLM_NAME=""               # required for --agent llm; same as the preset's ALIAS in scripts/serve_llm.sh
LLM_URL="http://127.0.0.1:8080"
THINKING="on"             # on | off; thinking is discarded after every reply either way
REASONING_EFFORT="medium" # Qwen3.8: low | medium | xhigh (its default, which adds "consider plausible alternatives"
                          # to the system prompt); medium adds nothing. Empty: the template's default
TEMPERATURE=""            # empty: the model's recommended value (recorded in params.json)
TOP_P=""                  # empty: the model's recommended value (recorded in params.json)
MAX_TOKENS="32768"        # per reply, thinking included
LLM_SEED=""               # empty: random, recorded in params.json

# --- garden ---
GARDEN_SIZE="10"
GROWTH_MIN="2"
GROWTH_MAX="6"
ENV_SEED=""               # empty: random, recorded in params.json

# --- user ---
GOALS="target:I:10"       # one goal per episode while testing; several: "target:I:10,time:S:40"
ALLERGY="none"            # e.g. nettle+chamomile

# --- episode ---
TURN_CAP="150"
PROMPT_FILE="prompts/system.txt"

# --- compaction (checked only between turns) ---
COMPACTOR="none"
CONTEXT_WINDOW=""         # model context size in tokens; required unless COMPACTOR=none
COMPACTION_TRIGGER="0.8"  # compact once the context passes this fraction of the window

# --- output ---
RUNS_DIR="runs"
TEMP_DIR="temp"

args=(
  --agent "$AGENT" --llm-url "$LLM_URL" --thinking "$THINKING" --max-tokens "$MAX_TOKENS"
  --garden-size "$GARDEN_SIZE" --growth-min "$GROWTH_MIN" --growth-max "$GROWTH_MAX"
  --goals "$GOALS" --allergy "$ALLERGY"
  --turn-cap "$TURN_CAP" --prompt-file "$PROMPT_FILE"
  --compactor "$COMPACTOR" --compaction-trigger "$COMPACTION_TRIGGER"
  --runs-dir "$RUNS_DIR" --temp-dir "$TEMP_DIR"
)
[[ -n "$LLM_NAME" ]] && args+=(--llm-name "$LLM_NAME")
[[ -n "$REASONING_EFFORT" ]] && args+=(--reasoning-effort "$REASONING_EFFORT")
[[ -n "$TEMPERATURE" ]] && args+=(--temperature "$TEMPERATURE")
[[ -n "$TOP_P" ]] && args+=(--top-p "$TOP_P")
[[ -n "$LLM_SEED" ]] && args+=(--llm-seed "$LLM_SEED")
[[ -n "$ENV_SEED" ]] && args+=(--env-seed "$ENV_SEED")
[[ -n "$CONTEXT_WINDOW" ]] && args+=(--context-window "$CONTEXT_WINDOW")

# Command-line arguments come last, so they override the defaults above.
python main.py "${args[@]}" "$@"
