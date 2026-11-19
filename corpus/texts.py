"""Layer 4 of the corpus pool: the texts (demo_spec.md, Sources), one folder per sheet in content/texts/:
<id>/metadata.json (what the source implies, corpus/metadata.py), <id>/<id>.txt (the text, once one passes)
and, while none has passed, <id>/failed.txt and failed.json (the last attempt and its problems).

A text file starts with a header (Title, Author, Kind), a blank line, then the body. In the body every
sentence ending in "." starts a new line, so the texts read easily (table rows are left alone).
"""

import json
import re
from pathlib import Path

from corpus.catalogue import CONTENT
from corpus.glossary import verbatim

TEXTS_DIR = CONTENT / "texts"
CUES_FILE = CONTENT / "cues.json"
HEADER = ("Title", "Author", "Kind")
KIND_NAMES = {"book": "monastery book", "transcript": "apothecary transcript", "herbal": "herbal lady tale",
              "pamphlet": "merchant pamphlet", "folk": "folk tale",
              "trials": "apothecary transcript"}          # a trial ledger is a transcript to the agent
REGISTRY_FILE = TEXTS_DIR / "registry.json"     # the cue spans of accepted texts, by effect
LENGTH_TOLERANCE = 0.15            # a text's words may differ from its sheet's target by this share


def load_cues() -> dict[str, list[str]]:
    return {k: v for k, v in json.loads(CUES_FILE.read_text(encoding="utf-8")).items() if k != "note"}


def split(text: str) -> tuple[dict[str, str], str]:
    head, body = text.split("\n\n", 1)
    fields = dict(line.split(": ", 1) for line in head.splitlines())
    return fields, body


NUMBERED = re.compile(r"^(?:[IVXLC]+|\d+)\. ")          # a section number: "IV. Of mixtures"


def one_sentence_per_line(body: str) -> str:
    """Break the line after every '.' that is followed by more text. Table rows and a heading's leading
    section number are left alone."""
    lines = []
    for line in body.splitlines():
        if line.startswith("|"):
            lines.append(line)
            continue
        number = NUMBERED.match(line)
        head, rest = (number.group(0), line[number.end():]) if number else ("", line)
        lines.append(head + re.sub(r"\.[ \t]+(?=\S)", ".\n", rest).rstrip())
    return "\n".join(lines).rstrip() + "\n"


def words(body: str) -> int:
    return len(re.findall(r"[\w']+", body))


def problems(path: Path, sheet: dict) -> list[str]:
    return problems_text(path.read_text(encoding="utf-8"), sheet)


def problems_text(text: str, sheet: dict) -> list[str]:
    """What is wrong with a text, mechanically: header, length, layout, glossary wording."""
    fields, body = split(text)
    out = []
    if tuple(fields) != HEADER:
        out.append(f"header {tuple(fields)}")
    n, target = words(body), sheet["words"]
    if abs(n - target) > LENGTH_TOLERANCE * target:
        out.append(f"{n} words, target {target}")
    if body != one_sentence_per_line(body):
        out.append("a sentence does not start its own line")
    if found := verbatim(body):
        out.append(f"glossary wording: {found}")
    return out


def folder_of(sheet_id: str) -> Path:
    return TEXTS_DIR / sheet_id.replace(":", "-")


def path_of(sheet_id: str) -> Path:
    folder = folder_of(sheet_id)
    return folder / f"{folder.name}.txt"


def failed_of(sheet_id: str) -> tuple[Path, Path]:
    """The last failed attempt at a source and its problems."""
    folder = folder_of(sheet_id)
    return folder / "failed.txt", folder / "failed.json"
