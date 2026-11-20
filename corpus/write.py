"""Layer 4 runner: writes the texts from the sheets with a local model (llama-server), piece by piece.

For every sheet, in order, one plant at a time (then the trial ledgers), after writing its metadata.json,
corpus/compose.py's steps: a header call (title, author, a cast), one call per claim (its sentences and one
marked sentence per effect), padding calls, then code assembles the text. Every piece is checked by code and
read alone by the blind reader (a fresh call that never sees the sheet, with the glossary only, as the agent
would); a failing piece is written again with its problems as feedback, up to --attempts times. The whole
text is then read once more. Each source has a folder content/texts/<id>/ with its metadata.json; an
accepted text is saved there as <id>.txt; a text that never passes is saved
there as failed.txt, with its problems in failed.json. Every call is logged to temp/corpus_write/<focus>.jsonl.

    python -m corpus.write --server http://127.0.0.1:8080 --plants mint
    python -m corpus.write --trials S D                           # trial ledgers (none given: all five)
    python -m corpus.write --dry-run --sheets folk:mint:01        # print the prompts, no server
"""

import argparse
import json
import os
import re
import sys
import time
import zlib
from pathlib import Path

from corpus import compose
from corpus.briefs import compare, items
from corpus.catalogue import load_plants
from corpus.compose import Piece
from corpus.glossary import entries, load_glossary
from corpus.metadata import write_metadata
from corpus.sheets import SHEETS_FILE
from corpus.texts import failed_of, load_cues, path_of, problems, problems_text
from environment.brewer import PLANTS

ROOT = Path(__file__).parent.parent
LOG_DIR = ROOT / "temp" / "corpus_write"
LOCK_FILE = ROOT / "temp" / "corpus_write.lock"
EXAMPLES = {"book": "book:mint:01", "transcript": "transcript:mint:04", "herbal": "herbal:mint:05",
            "pamphlet": "pamphlet:mint:13", "folk": "folk:mint:03", "trials": "trials:S"}
FINAL_ROUNDS = 2                # times the whole text may send pieces back after its final reading

STYLE = {
    "book": "a monastery treatise on one plant by a monk, in numbered sections with headings; methodical and "
            "plain; it reports what the house tried and saw.",
    "transcript": "an apothecary's ledger of trials: dated entries, each naming the plants brewed and who drank "
                  "it, then what was seen; terse, a little table-like; may end with a summary table in "
                  "Markdown (| Day | Herbs | What was seen |).",
    "herbal": "the rambling first-person reminiscence of an old herb-woman; the facts are buried among "
              "everyday life (hens, neighbours, weather, family) and told in passing.",
    "pamphlet": "a merchant's handbill: short, eager to sell, a greeting, a few bullet points, a closing line.",
    "trials": "an apothecary's ledger of trials of one kind of potion: dated entries, each naming the plants "
              "brewed, any brew poured into it, who drank it, and one piece of their work counted before and "
              "after drinking (stones lifted, sacks carried, sums worked), then what was noticed while drinking; "
              "terse, a little table-like; may end with a summary table in Markdown "
              "(| Day | Herbs | Before | After | Noticed |). Every entry brews the same plants of this one kind of "
              "potion: never suggest that one batch was made differently from another.",
    "folk": "a tale told second-hand at an inn or a fireside, with named locals; the facts come up in the "
            "story and are hedged as hearsay.",
}


# --- prompts --------------------------------------------------------------------------------------------


def glossary_text() -> str:
    g = load_glossary()
    lines = [g["note"], ""]
    for stat, e in g["stats"].items():
        lines.append(f"{stat} ({e['name']}). More: {'; '.join(e['more'])}. Less: {'; '.join(e['less'])}. "
                     f"Work that needs it, for example: {', '.join(e['trades'])}.")
    lines.append("")
    for label, e in g["labels"].items():
        lines.append(f"{label}: {'; '.join(e['cues'])}.")
    return "\n".join(lines)


READER_SYSTEM = """You read one source text from a medieval village, where potions are brewed from eight garden plants: {plants}. List every claim the text makes of the kinds below, including hearsay and claims you doubt. Report only what the text claims; never add outside knowledge or guesses about what a folk name or a place's plant is.

Kinds of claim, each as a JSON object:
- alias: the text says a name means one of the eight plants. {{"type": "alias", "name": "<the name>", "plant": "<plant>"}}
- place: a plant grows wild at a named place. {{"type": "place", "plant": "<plant>", "place": "<place>"}}
- soil: how a plant grows in an earth. {{"type": "soil", "plant": "<plant>", "earth": "black|brown|yellow", "growth": "dies|sometimes fails|fast|slow|ordinary"}}
- brew: plants brewed together, and what came of it. {{"type": "brew", "plants": ["<each plant exactly as the text names it: an official name, a folk name, or 'a plant of <place>'>"], "effects": [...]}}
- mix: two brews poured together. {{"type": "mix", "first": [<plants of the first brew>], "second": [<plants of the second brew, or 'all plants of <place>'>], "second_alone": [<effects of the second brew on its own, if the text gives them>], "mixed": [<effects of the mixed potion>]}}
- identity: the text says which plant a "plant of <place>" was. {{"type": "identity", "ref": "a plant of <place>", "plant": "<plant>"}}
- trial: someone's work counted before and after drinking a brew. Use this, not brew or mix, whenever the text gives both counts. {{"type": "trial", "plants": [<plants of the brew they drank>], "added": [[<plants of each brew poured into it>]], "before": <count>, "after": <count>, "effects": [<the stat letter if the work changed>, <each label noticed while drinking>]}}

Effects: a stat letter (S, D, V, I, W) when a drinker changed, whether they gained or lost; a label (fragrant, shimmering, sweet, bitter, murky, toxic) for what was noticed. Use the glossary to tell which. A brew the text says did nothing has "effects": [].

Glossary:
{glossary}

Answer with the JSON list of claims between <facts> and </facts>, and nothing else."""


def reader_system() -> str:
    return READER_SYSTEM.format(plants=", ".join(PLANTS), glossary=glossary_text())


# --- parsing --------------------------------------------------------------------------------------------


def _json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def parse_reader(raw: str) -> list:
    match = re.search(r"<facts>\s*(.*?)\s*</facts>", raw, re.S)
    text = match.group(1) if match else raw[raw.find("["): raw.rfind("]") + 1]
    facts = _json(text)
    if not isinstance(facts, list):
        raise ValueError("the reading is not a JSON list")
    return facts


# --- one sheet ------------------------------------------------------------------------------------------


def seed(sheet_id: str, part: str, role: str) -> int:
    return zlib.crc32(f"{sheet_id}:{part}:{role}".encode())


class Calls:
    """The model calls of one sheet, each logged with its part, attempt and problems."""

    def __init__(self, sheet: dict, writer, quick, reader, log):
        self.sheet, self.writer, self.quick, self.reader, self.log = sheet, writer, quick, reader, log
        self.count = 0

    def call(self, client, messages: list[dict], part: str, role: str):
        self.count += 1
        answer = client.complete(messages, seed(self.sheet["id"], f"{part}:{self.count}", role))
        record = {"sheet": self.sheet["id"], "part": part, "role": role, "content": answer.content,
                  "finish": answer.finish_reason, "thinking_chars": len(answer.reasoning or ""),
                  "seconds": answer.seconds, "usage": answer.usage}
        if not answer.content.strip():
            record["thinking_tail"] = (answer.reasoning or "")[-3000:]
        return answer, record

    def write(self, record: dict, problems: list[str]) -> None:
        record["problems"] = problems
        self.log.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.log.flush()

    def read(self, text: str, expected: list[dict], part: str) -> list[str]:
        """The blind reader's problems with a text (or a piece of one) against the claims it should make."""
        answer, record = self.call(self.reader, [{"role": "system", "content": reader_system()},
                                                 {"role": "user", "content": text}], part, "reader")
        try:
            found = compare(expected, parse_reader(answer.content))
        except (ValueError, json.JSONDecodeError) as err:
            found = [f"(the reader's answer could not be parsed: {err}; try again)"]
        self.write(record, found)
        return found


def _example(sheet: dict) -> str | None:
    example_id = EXAMPLES[sheet["kind"]]
    path = path_of(example_id)
    return path.read_text(encoding="utf-8") if example_id != sheet["id"] and path.exists() else None


def write_header(calls: Calls, attempts: int) -> tuple[dict | None, list[str]]:
    sheet = calls.sheet
    places = list(load_plants()["groups"])
    problems: list[str] = []
    for attempt in range(1, attempts + 1):
        prompt = compose.header_prompt(sheet, STYLE[sheet["kind"]], places, problems)
        answer, record = calls.call(calls.quick, [{"role": "user", "content": prompt}], "header", "writer")
        try:
            header = compose.parse_header(answer.content)
            problems = compose.check_names(" ".join(header.values()), sheet)
        except ValueError as err:
            header, problems = None, [str(err)]
        calls.write(record, problems)
        if not problems:
            return header, []
    return None, [f"header: {p}" for p in problems]


def write_piece(calls: Calls, system: str, piece: Piece, samples: dict, attempts: int) -> bool:
    piece.attempts, piece.done = 0, False
    while piece.attempts < attempts:
        piece.attempts += 1
        user = compose.piece_prompt(piece, samples)
        answer, record = calls.call(calls.writer, [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}], piece.item["n"], "writer")
        try:
            piece.text = compose.parse_piece(answer.content)
        except ValueError as err:
            piece.problems = [str(err)]
            calls.write(record, piece.problems)
            continue
        problems = compose.check_names(piece.text, calls.sheet) + compose.check_brew_names(piece.text, piece.item)
        calls.write(record, problems)
        if not problems:
            problems = calls.read(piece.text, [piece.item], piece.item["n"])
        piece.problems = problems
        if not problems:
            piece.done = True
            return True
    return False


def write_pad(calls: Calls, system: str, index: int, words: int, last: int, attempts: int,
              problems: list[str] | None = None) -> str | None:
    role = "the opening" if index == 0 else "the closing passage" if index == last else "a passage between the claims"
    topic = compose.PAD_TOPICS[(zlib.crc32(calls.sheet["id"].encode()) + index) % len(compose.PAD_TOPICS)]
    problems = list(problems or [])
    for _ in range(attempts):
        answer, record = calls.call(calls.quick, [{"role": "system", "content": system},
                                                  {"role": "user", "content": compose.pad_prompt(words, topic, role, problems)}],
                                    f"pad{index}", "writer")
        try:
            text = compose.parse_pad(answer.content)
            problems = compose.check_names(text, calls.sheet)
        except ValueError as err:
            text, problems = None, [str(err)]
        calls.write(record, problems)
        if not problems:
            return text
    return None


def write_sheet(sheet: dict, writer, quick, reader, attempts: int, log) -> bool:
    write_metadata(sheet)                     # what the source must imply, before any text exists
    calls = Calls(sheet, writer, quick, reader, log)
    start = time.monotonic()
    header, problems = write_header(calls, attempts)
    text = ""
    if header:
        system = compose.system_prompt(sheet, header, STYLE[sheet["kind"]], glossary_text(),
                                       _example(sheet))
        pieces = [Piece(item) for item in items(sheet)]
        samples = load_cues()
        for piece in pieces:
            write_piece(calls, system, piece, samples, attempts)
        plan = compose.pad_plan(sheet)
        pads = [write_pad(calls, system, i, w, len(plan) - 1, attempts) for i, w in enumerate(plan)]
        problems = [q if compose.piece_of(q) == p.item['n'] else f"{p.item['n']}: {q}" for p in pieces if not p.done for q in p.problems]
        problems += [f"padding passage {i}: could not be written" for i, pad in enumerate(pads) if pad is None]
        for _ in range(FINAL_ROUNDS if not problems else 0):
            text = compose.assemble(sheet, header, pieces, pads)
            problems = problems_text(text, sheet) + calls.read(text, items(sheet), "whole")
            if not problems:
                break
            redo = {compose.piece_of(p) for p in problems} - {None}
            for piece in pieces:                          # a claim the whole text gets wrong: write it again
                if piece.item["n"] in redo:
                    piece.problems = [p for p in problems if compose.piece_of(p) == piece.item["n"]]
                    write_piece(calls, system, piece, samples, attempts)
            if any(compose.piece_of(p) is None for p in problems):   # a claim nobody asked for: find its padding
                for i, pad in enumerate(pads):
                    found = calls.read(pad, [], f"pad{i}")
                    if found:
                        pads[i] = write_pad(calls, system, i, plan[i], len(plan) - 1, attempts,
                                            [f"it made a claim: {p}" for p in found]) or pad
        if header and not problems:
            text = compose.assemble(sheet, header, pieces, pads)
    minutes = (time.monotonic() - start) / 60
    if not problems:
        path_of(sheet["id"]).write_text(text, encoding="utf-8")
        for path in failed_of(sheet["id"]):
            path.unlink(missing_ok=True)
        print(f"  {sheet['id']}: accepted ({calls.count} calls, {minutes:.1f} min)", flush=True)
        return True
    failed_text, failed_problems = failed_of(sheet["id"])
    if header and text:
        failed_text.write_text(text, encoding="utf-8")
    failed_problems.write_text(json.dumps(problems, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {sheet['id']}: failed, {len(problems)} problems ({calls.count} calls, {minutes:.1f} min)", flush=True)
    return False


# --- the run --------------------------------------------------------------------------------------------


def select(args) -> list[dict]:
    sheets = json.loads(SHEETS_FILE.read_text(encoding="utf-8"))
    if args.sheets:
        chosen = [s for s in sheets if s["id"] in set(args.sheets)]
        if len(chosen) != len(set(args.sheets)):
            sys.exit(f"unknown sheet ids: {sorted(set(args.sheets) - {s['id'] for s in chosen})}")
        return chosen
    if args.plants is None and args.trials is None:            # everything: every plant, then the ledgers
        args.plants, args.trials = list(PLANTS), []
    order = args.plants or []
    if unknown := [p for p in order if p not in PLANTS]:
        sys.exit(f"unknown plants: {unknown}")
    chosen = [s for p in order for s in sheets if s["focus"] == p and s["kind"] != "trials"]
    if args.trials is not None:
        stats = args.trials or [s["focus"] for s in sheets if s["kind"] == "trials"]
        chosen += [s for stat in stats for s in sheets if s["kind"] == "trials" and s["focus"] == stat]
    return chosen


def done(sheet: dict) -> bool:
    path = path_of(sheet["id"])
    return path.exists() and not problems(path, sheet)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="qwen3.8-27b-q8", help="the server's model alias")
    parser.add_argument("--plants", nargs="*", help="focus plants, in order (default: all eight)")
    parser.add_argument("--trials", nargs="*", help="trial ledgers of these stats (none given: all five)")
    parser.add_argument("--sheets", nargs="*", help="sheet ids instead of whole plants")
    parser.add_argument("--attempts", type=int, default=3, help="per piece (and per header or padding passage)")
    parser.add_argument("--force", action="store_true", help="rewrite texts that already pass")
    parser.add_argument("--writer-thinking", choices=("on", "off"), default="on")
    parser.add_argument("--reader-thinking", choices=("on", "off"), default="on")
    parser.add_argument("--reasoning-effort", default="low", help="Qwen3.8: low | medium | xhigh")
    parser.add_argument("--writer-max-tokens", type=int, default=16384, help="per piece, thinking included")
    parser.add_argument("--quick-max-tokens", type=int, default=4096,
                        help="header and padding calls, which run without thinking")
    parser.add_argument("--reader-max-tokens", type=int, default=24576, help="thinking included")
    parser.add_argument("--reader-temperature", type=float, default=0.0,
                        help="0: the reader decodes greedily, so a text's verdict does not depend on chance "
                             "(the writer keeps the model's recommended sampling)")
    parser.add_argument("--dry-run", action="store_true", help="print the first sheet's prompts and stop")
    args = parser.parse_args(argv)

    sheets = [s for s in select(args) if args.force or not done(s)]
    if args.dry_run:
        if not sheets:
            print("nothing to write")
            return 0
        sheet = sheets[0]
        header = {"title": "<title>", "author": "<author>", "people": "<people>", "setting": "<setting>"}
        system = compose.system_prompt(sheet, header, STYLE[sheet["kind"]], glossary_text(),
                                       _example(sheet))
        print("=== HEADER ===\n" + compose.header_prompt(sheet, STYLE[sheet["kind"]],
                                                       list(load_plants()["groups"]), []),
              "\n\n=== SYSTEM (every piece and padding passage) ===\n" + system)
        for item in items(sheet):
            print(f"\n=== PIECE {item['n']} ===\n" + compose.piece_prompt(Piece(item), load_cues()))
        plan = compose.pad_plan(sheet)
        print("\n=== PADDING (first of {}) ===\n".format(len(plan)) +
              compose.pad_prompt(plan[0], compose.PAD_TOPICS[0], "the opening", []))
        print("\n=== READER ===\n" + reader_system())
        return 0

    from LLM.client import ChatClient   # only needed with a server

    def client(thinking: str, max_tokens: int, temperature: float | None = None) -> ChatClient:
        return ChatClient(args.server, args.model, max_tokens, temperature=temperature, thinking=thinking == "on",
                          reasoning_effort=args.reasoning_effort, timeout=1800)

    writer = client(args.writer_thinking, args.writer_max_tokens)
    quick = client("off", args.quick_max_tokens)
    reader = client(args.reader_thinking, args.reader_max_tokens, args.reader_temperature)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        lock = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit(f"another run holds {LOCK_FILE} (two runs would write the same folders); delete it if stale")
    os.write(lock, str(os.getpid()).encode())
    os.close(lock)
    try:
        print(f"server: {json.dumps(writer.server_info())}", flush=True)
        results: dict[str, list[bool]] = {}
        start = time.monotonic()
        for plant in dict.fromkeys(s["focus"] for s in sheets):
            todo = [s for s in sheets if s["focus"] == plant]
            print(f"{plant}: {len(todo)} sheets", flush=True)
            with open(LOG_DIR / f"{plant}.jsonl", "a", encoding="utf-8") as log:
                results[plant] = [write_sheet(s, writer, quick, reader, args.attempts, log) for s in todo]
            print(f"{plant}: {sum(results[plant])} accepted, {results[plant].count(False)} failed "
                  f"({(time.monotonic() - start) / 60:.0f} min so far)", flush=True)
    finally:
        LOCK_FILE.unlink(missing_ok=True)
    return 0 if all(all(r) for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
