"""Per-turn checkpoints: save the full state atomically; restore it and cut the logs back."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from environment.world import World
from ledger import Ledger

CHECKPOINT = "checkpoint.json"
LOG_FILES = ("transcript.md", "actions.jsonl", "ledger.jsonl")
VERSION = 1


@dataclass(frozen=True)
class Checkpoint:
    world: dict
    ledger: dict
    agent: dict           # agent state (conversation, RNG state, ...)
    log_sizes: dict[str, int]
    compactions: int      # compaction files written so far


def save(
    temp_dir: Path, run_dir: Path, world: World, ledger: Ledger, agent: dict[str, Any], compactions: int
) -> None:
    """Write the checkpoint atomically (a crash while saving keeps the previous one)."""
    sizes = {name: (run_dir / name).stat().st_size if (run_dir / name).exists() else 0 for name in LOG_FILES}
    data = {
        "version": VERSION,
        "world": world.to_dict(),
        "ledger": ledger.to_dict(),
        "agent": agent,
        "log_sizes": sizes,
        "compactions": compactions,
    }
    tmp = temp_dir / (CHECKPOINT + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, temp_dir / CHECKPOINT)


def load(temp_dir: Path) -> Checkpoint | None:
    path = temp_dir / CHECKPOINT
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != VERSION:
        raise ValueError(f"Unsupported checkpoint version {data.get('version')}.")
    return Checkpoint(data["world"], data["ledger"], data["agent"], data["log_sizes"], data["compactions"])


def restore(cp: Checkpoint, run_dir: Path, kb_path: Path) -> tuple[World, Ledger]:
    """Cut logs and compaction files back to the checkpoint; rebuild world and ledger."""
    for name, size in cp.log_sizes.items():
        path = run_dir / name
        if path.exists() and path.stat().st_size > size:
            with path.open("r+b") as f:
                f.truncate(size)
    for extra in sorted((run_dir / "compactions").glob("*.json")):
        if int(extra.stem) > cp.compactions:
            extra.unlink()
    return World.from_dict(cp.world, str(kb_path)), Ledger.from_dict(cp.ledger)
