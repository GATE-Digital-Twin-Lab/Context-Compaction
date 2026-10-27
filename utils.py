"""Generic helpers."""

import json
import re
import secrets
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
