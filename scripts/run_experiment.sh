#!/usr/bin/env bash
# Run one Potion Garden episode.
# Every parameter is listed below with its default; override any of them on the command line, e.g.
#   scripts/run_experiment.sh --garden-size 12 --goals "time:S:30,target:I:10" --env-seed 7
set -euo pipefail
cd "$(dirname "$0")/.."

# --- agent ---
AGENT="random"            # llm | random | oracle
LLM_NAME=""               # required for --agent llm
TEMPERATURE="0.7"
MAX_TOKENS="1024"
LLM_SEED=""               # empty: random, recorded in params.json

# --- garden ---
GARDEN_SIZE="10"
GROWTH_MIN="2"
GROWTH_MAX="6"
ENV_SEED=""               # empty: random, recorded in params.json

# --- user ---
GOALS="target:I:10,time:S:40,target:D:10"
ALLERGY="none"            # e.g. p3+p5

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
  --agent "$AGENT" --temperature "$TEMPERATURE" --max-tokens "$MAX_TOKENS"
  --garden-size "$GARDEN_SIZE" --growth-min "$GROWTH_MIN" --growth-max "$GROWTH_MAX"
  --goals "$GOALS" --allergy "$ALLERGY"
  --turn-cap "$TURN_CAP" --prompt-file "$PROMPT_FILE"
  --compactor "$COMPACTOR" --compaction-trigger "$COMPACTION_TRIGGER"
  --runs-dir "$RUNS_DIR" --temp-dir "$TEMP_DIR"
)
[[ -n "$LLM_NAME" ]] && args+=(--llm-name "$LLM_NAME")
[[ -n "$LLM_SEED" ]] && args+=(--llm-seed "$LLM_SEED")
[[ -n "$ENV_SEED" ]] && args+=(--env-seed "$ENV_SEED")
[[ -n "$CONTEXT_WINDOW" ]] && args+=(--context-window "$CONTEXT_WINDOW")

# Command-line arguments come last, so they override the defaults above.
python main.py "${args[@]}" "$@"
