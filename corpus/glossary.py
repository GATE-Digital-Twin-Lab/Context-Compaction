"""The glossary (demo_spec.md, Requests): signs and uses that point to a stat, and cues that point to a
secondary label. It is shown to the agent; texts and requests must say the same things in other words,
so they never repeat a glossary phrase or name a stat or label outright (see verbatim()).
"""

import json
import re

from corpus.catalogue import CONTENT

GLOSSARY_FILE = CONTENT / "glossary.json"


def load_glossary() -> dict:
    return json.loads(GLOSSARY_FILE.read_text(encoding="utf-8"))


def entries(glossary: dict | None = None) -> dict[str, list[str]]:
    """Every phrase of the glossary, by the stat or label it points to: names, direct words, signs,
    trades and cues, and for a label its near words (the cues' own images, e.g. "honey"), which a text
    must not borrow either."""
    glossary = glossary or load_glossary()
    out = {}
    for stat, e in glossary["stats"].items():
        out[stat] = [e["name"]] + e["words"] + e["more"] + e["less"] + e["trades"]
    for label, e in glossary["labels"].items():
        out[label] = [label] + e["words"] + e["cues"] + e.get("near", [])
    return out


def verbatim(text: str, glossary: dict | None = None) -> list[str]:
    """The glossary phrases a text repeats word for word (case and spacing ignored)."""
    flat = re.sub(r"\s+", " ", text.lower())
    return sorted({phrase for phrases in entries(glossary).values() for phrase in phrases
                   if re.search(r"(?<![\w'])" + re.escape(phrase.lower()) + r"(?![\w'])", flat)})


def prompt_text(glossary: dict | None = None) -> str:
    """The glossary as the agent sees it: per stat its words, signs of more and less, and trades; per label
    its words and cues. The near words are a writer's list and stay hidden."""
    glossary = glossary or load_glossary()
    lines = [glossary["note"], "", "Stats (signs of more; signs of less; trades that need it):"]
    for stat, e in glossary["stats"].items():
        lines.append(f"- {stat}, {e['name']} ({', '.join(e['words'])}): more: {'; '.join(e['more'])}. "
                     f"Less: {'; '.join(e['less'])}. Trades: {', '.join(e['trades'])}.")
    lines += ["", "Secondary effects (noticed in the potion itself):"]
    for label, e in glossary["labels"].items():
        lines.append(f"- {label} ({', '.join(e['words'])}): e.g. {'; '.join(e['cues'])}.")
    return "\n".join(lines)
