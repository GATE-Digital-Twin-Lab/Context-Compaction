"""The agent's notes in the fixed reply schema (prompts/system.txt, "Reply format"): every line of a reply
sorted into its section and sub-section, with the departures from the schema. Nothing is reported back
to the agent; the schema is only checked. Run as a command to write notes.jsonl for recorded runs:
    python -m LLM.notes RUN_DIR [RUN_DIR ...]"""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from utils import transcript_blocks

SCHEMA: dict[str, tuple[str, ...]] = {
    "Results": ("Potions", "Growth", "Lore"),
    "State": ("Garden", "Inventory", "Logged", "Best"),
    "Beliefs": ("Confirmed", "Hypotheses", "Refuted"),
    "Plan": ("Next", "Then"),
}
SECTION_OF = {sub: section for section, subs in SCHEMA.items() for sub in subs}   # sub-section names are unique
ORDER = [(section, sub) for section, subs in SCHEMA.items() for sub in subs]
NONE = "none"

_HEADING = re.compile(r"^[#*_\s]*([A-Za-z]+)[*_\s]*:[*_\s]*(.*)$")
_BULLET = re.compile(r"^[-*•]\s+(.*)$")


@dataclass(frozen=True)
class Item:
    section: str
    sub: str
    text: str


@dataclass
class Notes:
    items: list[Item] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)      # sub-sections written as "- none"
    missing: list[str] = field(default_factory=list)    # sub-sections not written at all
    problems: list[str] = field(default_factory=list)   # other departures from the schema

    @property
    def valid(self) -> bool:
        return not self.missing and not self.problems

    def grouped(self) -> dict[str, dict[str, list[str]]]:
        out: dict[str, dict[str, list[str]]] = {s: {sub: [] for sub in subs} for s, subs in SCHEMA.items()}
        for item in self.items:
            out[item.section][item.sub].append(item.text)
        return out


def notes_text(reply: str) -> str:
    """The reply up to its JSON call (the first line that starts with '{')."""
    lines = reply.split("\n")
    end = next((i for i, line in enumerate(lines) if line.lstrip().startswith("{")), len(lines))
    return "\n".join(lines[:end])


def parse_notes(reply: str) -> Notes:
    notes = Notes()
    section: str | None = None
    sub: str | None = None
    seen: list[tuple[str, str]] = []
    last: int | None = None   # index of the last item, for wrapped lines

    def add(text: str) -> None:
        nonlocal last
        text = text.strip()
        if sub is None:
            notes.problems.append(f"line outside any sub-section: {text[:80]!r}")
            return
        if text.strip(" .").lower() == NONE:
            notes.empty.append(sub)
            last = None
            return
        notes.items.append(Item(section, sub, text))
        last = len(notes.items) - 1

    for raw in notes_text(reply).split("\n"):
        line = raw.strip()
        if not line:
            continue
        heading = _HEADING.match(line)
        name = heading.group(1) if heading else None
        if name in SCHEMA:
            section, sub, last = name, None, None
            if heading.group(2).strip():
                notes.problems.append(f"text on the {name} heading: {heading.group(2).strip()[:80]!r}")
            continue
        if name in SECTION_OF:
            if section != SECTION_OF[name]:
                notes.problems.append(f"{name} outside {SECTION_OF[name]}")
                section = SECTION_OF[name]
            sub, last = name, None
            if (sub_section := (section, sub)) in seen:
                notes.problems.append(f"{sub} written twice")
            seen.append(sub_section)
            rest = heading.group(2).strip()
            if rest:
                bullet = _BULLET.match(rest)
                add(bullet.group(1) if bullet else rest)
            continue
        if bullet := _BULLET.match(line):
            add(bullet.group(1))
        elif last is not None and raw[:1].isspace():   # an indented line continues the item above
            item = notes.items[last]
            notes.items[last] = Item(item.section, item.sub, f"{item.text} {line}")
        else:
            notes.problems.append(f"not in the schema: {line[:80]!r}")

    notes.missing = [sub for section, sub in ORDER if (section, sub) not in seen]
    present = [pair for pair in seen if pair in ORDER]
    if present != sorted(set(present), key=ORDER.index):
        notes.problems.append("sub-sections out of order")
    return notes


def write_notes(run_dir: Path) -> Path:
    """notes.jsonl: the parsed notes of every agent reply in transcript_clean.md, in order."""
    text = (run_dir / "transcript_clean.md").read_text(encoding="utf-8")
    path = run_dir / "notes.jsonl"
    with path.open("w", encoding="utf-8") as f:
        reply = 0
        for turn, role, content in transcript_blocks(text):
            if role != "agent":
                continue
            reply += 1
            notes = parse_notes(content)
            record = {"turn": turn, "reply": reply, "valid": notes.valid, **asdict(notes)}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def main(argv: list[str]) -> None:
    for arg in argv:
        path = write_notes(Path(arg))
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        valid = sum(r["valid"] for r in records)
        print(f"{path}: {len(records)} replies, {valid} follow the schema")


if __name__ == "__main__":
    main(sys.argv[1:])
