"""Generic helpers. Run as a command to write transcript_clean.md for older runs:
    python utils.py [RUN_DIR or RUNS_ROOT ...]   (default: runs/)"""

import json
import re
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def slugify(name: str) -> str:
    """Make a name safe for a folder: 'Qwen/Qwen3-8B' -> 'Qwen_Qwen3-8B'."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return slug or "unnamed"


def new_seed() -> int:
    """A random seed (recorded in params.json so the run can be repeated)."""
    return secrets.randbelow(2**31)


def run_id(now: datetime | None = None) -> str:
    """Timestamp plus a short random suffix, so parallel runs never collide."""
    now = now or datetime.now()
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: Any) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


# --- clean transcript: transcript.md without the discarded thinking ----------

THINKING_ROLE = "agent (thinking, discarded)"
ROLES = ("user", "environment", "agent", THINKING_ROLE)
CLEAN_NOTE = "Only what stays in the agent's context: the thinking, discarded after every reply, is left out."

_BOUNDARY = re.compile(r"^(## Turn \d+|\*\*(" + "|".join(re.escape(r) for r in ROLES) + r")\*\*)$")


def clean_transcript(text: str) -> str:
    """Drop every thinking block (its role line up to the next role line or turn heading)."""
    kept, skipping = [], False
    for line in text.split("\n"):
        if _BOUNDARY.match(line):
            skipping = line == f"**{THINKING_ROLE}**"
        if not skipping:
            kept.append(line)
    title, _, rest = "\n".join(kept).partition("\n")
    return f"{title} (clean)\n\n{CLEAN_NOTE}\n{rest}"


def write_clean_transcript(run_dir: Path) -> Path:
    """Write transcript_clean.md next to transcript.md; return its path."""
    path = run_dir / "transcript_clean.md"
    path.write_text(clean_transcript((run_dir / "transcript.md").read_text(encoding="utf-8")), encoding="utf-8")
    return path


def clean_transcripts(paths: list[str]) -> None:
    """Write the clean transcript of every run under the given folders (default: runs/)."""
    for root in map(Path, paths or ["runs"]):
        for transcript in sorted(root.rglob("transcript.md")):
            print(write_clean_transcript(transcript.parent))


if __name__ == "__main__":
    clean_transcripts(sys.argv[1:])
