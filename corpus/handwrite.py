"""Layer 4 by hand: the texts are written one by one by Claude (Claude Code), not by the local model.

    python -m corpus.handwrite next          # the brief of the first sheet that has no text yet
    python -m corpus.handwrite brief <id>    # the brief of one sheet (e.g. folk:mint:03)
    python -m corpus.handwrite check <id>    # puts one sentence per line, then checks the text
    python -m corpus.handwrite status        # how many texts are written, by kind

A text is written to content/texts/<id>/<id>.txt (Title, Author, Kind, then the body). It must make every
claim of its brief as told (false ones included: they are the source's myths) and no other claim. The check
is mechanical: header and layout, no plant, folk name or place the sheet does not use, and every brew's
names present somewhere in the text.
"""

import json
import re
import sys
from collections import Counter

from corpus.briefs import allowed_names, items, norm, stray_names
from corpus.catalogue import load_plants
from corpus.compose import brew_names
from corpus.sheets import SHEETS_FILE
from corpus.texts import KIND_NAMES, folder_of, one_sentence_per_line, path_of, problems_text, split, words
from corpus.write import STYLE


def sheets() -> list[dict]:
    return json.loads(SHEETS_FILE.read_text(encoding="utf-8"))


def by_id(sheet_id: str) -> dict:
    return next(s for s in sheets() if s["id"] == sheet_id)


def brief(sheet: dict) -> str:
    meta = json.loads((folder_of(sheet["id"]) / "metadata.json").read_text(encoding="utf-8"))
    truth = {c["n"]: c["true"] for c in meta["claims"]}
    lines = [f"{sheet['id']}: {KIND_NAMES[sheet['kind']]}, about {sheet['words']} words "
             f"(padding {round(100 * sheet['padding'])}%)", f"Style: {STYLE[sheet['kind']]}", ""]
    for item in items(sheet):
        mark = "" if truth.get(item["n"], True) else "  [myth: write it as told]"
        lines.append(f"{item['n']}: {item['brief']}{mark}")
    if false := meta["false claims"]:
        lines += ["", "False claims (for reference):"] + [f"  {f['n']}: {f['issue']}" for f in false]
    return "\n".join(lines)


def check(sheet: dict) -> list[str]:
    path = path_of(sheet["id"])
    text = path.read_text(encoding="utf-8")
    fields, body = split(text)
    fixed = "\n".join(f"{k}: {v}" for k, v in fields.items()) + "\n\n" + one_sentence_per_line(body)
    if fixed.strip() != text.strip():
        path.write_text(fixed.rstrip() + "\n", encoding="utf-8")
        text = fixed
    out = problems_text(text, sheet)
    if any("..." in v for v in fields.values()):
        out.append("a header field has '...' in it (a slip): fix it")
    if stray := stray_names(text, sheet):
        out.append(f"names this text must not use: {stray}")
    own = allowed_names(sheet)["aliases"]
    for root, alias in echoes():
        if norm(alias) not in own and len(re.findall(rf"\b{root}\b", text)) > len(re.findall(re.escape(alias), text, re.I)):
            out.append(f"the name {root} echoes the folk name {alias}: pick another")
    plain = text.lower().replace("’", "'")
    for item in items(sheet):
        if missing := [n for n in brew_names(item) if n not in plain]:
            out.append(f"{item['n']}: never names {', '.join(missing)}")
    print(f"{sheet['id']}: {words(split(text)[1])} words (target {sheet['words']})")
    return out


def echoes() -> list[tuple[str, str]]:
    """The person's name inside each folk name (Remy in "Remy's herb"): a cast member who shares it would
    read as a hint."""
    out = []
    for aliases in load_plants()["aliases"].values():
        for alias in aliases:
            if "'s " in alias:
                out.append((alias.split("'s ")[0].split()[-1], alias))
    for place in load_plants()["groups"]:
        if " " in place and not place.startswith("the "):
            out.append((place.split("'s")[0].split()[0], place))
    return out


def main(argv: list[str]) -> None:
    command = argv[0] if argv else "next"
    if command == "status":
        all_sheets = sheets()
        done = [s for s in all_sheets if path_of(s["id"]).exists()]
        print(f"{len(done)} of {len(all_sheets)} written:", dict(Counter(s["kind"] for s in done)))
    elif command == "next":
        todo = next((s for s in sheets() if not path_of(s["id"]).exists()), None)
        print(brief(todo) if todo else "every sheet has a text")
    elif command == "brief":
        print(brief(by_id(argv[1])))
    elif command == "check":
        problems = check(by_id(argv[1]))
        print("\n".join(problems) if problems else "ok")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
