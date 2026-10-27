#!/usr/bin/env bash
# Continue an interrupted run from its last checkpoint, with its saved parameters:
#   scripts/resume.sh runs/<agent>/<run_id>
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -ne 1 ]]; then
  echo "usage: scripts/resume.sh runs/<agent>/<run_id>" >&2
  exit 2
fi
python main.py --resume "$1"
