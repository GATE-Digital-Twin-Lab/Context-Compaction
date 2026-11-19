"""Layer 4 runner: writes the texts from the sheets with a local model (llama-server), checks them, retries.

For every sheet, in order, one plant at a time (then the trial ledgers), after writing its metadata.json:
  1. write: the writer gets the sheet's brief, the rules, the glossary, a text of the same kind as a style
     example, and the images already used for its effects; it returns the text and, for every effect, the
     words that show it (the cue spans);
  2. check (code): header, length, layout, no glossary wording, no stray names, every cue span present and
     new (not close to an earlier text's span for the same effect);
  3. read (a fresh call that never sees the sheet): the reader lists every claim it finds, with the glossary
     only, as the agent would;
  4. compare (code): every claim of the brief found with its value, nothing else found.
A failure goes back to the writer as feedback, up to --attempts times. Each source has a folder
content/texts/<id>/ with its metadata.json; an accepted text is saved there as <id>.txt and its spans join
the registry; a text that never passes is saved there as failed.txt, with its problems in failed.json.
Every call is logged to temp/corpus_write/<plant>.jsonl. Each request starts a fresh conversation, so
no context builds up between sheets.

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

from corpus.briefs import brief, check_cues, compare, items, stray_names
from corpus.glossary import entries, load_glossary
from corpus.sheets import SHEETS_FILE
from corpus.metadata import write_metadata
from corpus.texts import (KIND_NAMES, REGISTRY_FILE, failed_of, load_cues, one_sentence_per_line, path_of,
                          problems, problems_text)
from environment.brewer import PLANTS

ROOT = Path(__file__).parent.parent
LOG_DIR = ROOT / "temp" / "corpus_write"
LOCK_FILE = ROOT / "temp" / "corpus_write.lock"
EXAMPLES = {"book": "book:mint:01", "transcript": "transcript:mint:04", "herbal": "herbal:mint:05",
            "pamphlet": "pamphlet:mint:13", "folk": "folk:mint:03", "trials": "trials:S"}
RECENT = 40                     # earlier images per effect shown to the writer (all are checked)

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


def banned_words() -> str:
    return ", ".join(sorted({p for phrases in entries().values() for p in phrases}, key=str.lower))


def writer_system(sheet: dict) -> str:
    words, padding = sheet["words"], round(sheet["padding"] * 100)
    examples = "\n".join(f"- {label}: {'; '.join(cues[:3])}" for label, cues in load_cues().items())
    return f"""You write source texts for a game set in a medieval village, where people brew potions from eight garden plants: {', '.join(PLANTS)}. A player will later read your text and must work out, from your descriptions alone, what it claims. The claims you must make are given as a numbered brief.

Rules:
1. Make every claim of the brief, and no other claim. A claim is: what a folk name means, where a plant grows wild, how a plant grows in one of the three earths (black, brown, yellow), what a brew of plants does, what a mix of two brews does, or a trial (someone's work counted before and after drinking a brew). Never add another such claim, true or not, even in passing.
2. Everything else is padding: everyday life, people, weather, trade, the author's habits. Padding must never hint at an effect: no tastes, smells, warmth or cold felt by anyone, no illness, recovery or tiredness, no change in anyone's body, mind or skill. Padding names no plant, folk name or place that the brief does not use.
3. Never use any of these words or phrases, which belong to the glossary below: {banned_words()}.
4. Show every effect through an image of your own: what people saw, felt or noticed. A stat effect is a change in someone who drank the potion, a gain or a loss as suits the story; never name the stat. A secondary effect is shown through what people noticed (the glossary says what each one means). Each image must be new: different from the images listed as already used, and different from the other images in your text.
5. Never give amounts, counts or proportions of plants. A brew is just the plants "together". The only numbers about a potion's effect are the two counts of work a trial in the brief gives, used exactly.
6. Use plant names, folk names and places exactly as the brief gives them. When the brief gives a folk name or "a plant of <place>", never reveal which plant it is.
7. Length: about {words} words, of which about {padding}% is padding.

Glossary (the player has it; you must not copy its words):
{glossary_text()}

Kinds of image that work (never copy these either; find your own):
{examples}

The text is {"an" if KIND_NAMES[sheet['kind']][0] in "aeiou" else "a"} {KIND_NAMES[sheet['kind']]}: {STYLE[sheet['kind']]}

Answer in exactly this form:
TITLE: <title>
AUTHOR: <who wrote or told it, e.g. a name and a role>
<text>
<the text; plain paragraphs, no title line>
</text>
<cues>
[{{"fact": "F1", "effect": "<the label, or the stat letter>", "span": "<the exact words of your text that show it>"}}]
</cues>
Give one cues entry for every effect of every brew and mix in the brief (none for a brew where nothing happens); a mix's second brew on its own and the mixed potion each need their own. For a trial, give one for every label noticed while drinking (the change in the work needs none)."""


def writer_user(sheet: dict, registry: dict[str, list[str]], feedback: list[str]) -> str:
    example_id = EXAMPLES[sheet["kind"]]
    parts = []
    if example_id != sheet["id"] and path_of(example_id).exists():
        parts.append("A text of the same kind, for its style only (its claims and images are not yours, do not "
                     "reuse them):\n<example>\n" + path_of(example_id).read_text(encoding="utf-8") + "</example>")
    focus = f"trials of one kind of potion" if sheet["kind"] == "trials" else f"focus plant: {sheet['focus']}"
    parts.append(f"The brief for your text ({focus}):\n{brief(sheet)}")
    effects = sorted({e for item in items(sheet) for e in item["cues"]})
    used = [f"- {e}: " + " | ".join(registry.get(e, [])[-RECENT:]) for e in effects if registry.get(e)]
    if used:
        parts.append("Images already used for these effects; do not reuse them or anything close:\n" + "\n".join(used))
    if feedback:
        parts.append("Your previous attempt was rejected. Fix these problems:\n" + "\n".join(f"- {p}" for p in feedback))
    return "\n\n".join(parts)


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


def parse_writer(raw: str) -> tuple[str, str, str, list]:
    """Title, author, body and cue entries of a writer's answer; ValueError naming what is missing."""
    title = re.search(r"^\s*TITLE:\s*(.+?)\s*$", raw, re.M)
    author = re.search(r"^\s*AUTHOR:\s*(.+?)\s*$", raw, re.M)
    body = re.search(r"<text>\s*(.*?)\s*</text>", raw, re.S)
    cues = re.search(r"<cues>\s*(.*?)\s*</cues>", raw, re.S)
    missing = [n for n, m in (("TITLE", title), ("AUTHOR", author), ("<text>", body), ("<cues>", cues)) if not m]
    if missing:
        raise ValueError(f"the answer lacks {', '.join(missing)}")
    try:
        cue_list = _json(cues.group(1))
    except json.JSONDecodeError as err:
        raise ValueError(f"the <cues> list is not valid JSON: {err}") from None
    if not isinstance(cue_list, list):
        raise ValueError("<cues> must be a JSON list")
    return title.group(1), author.group(1), body.group(1), cue_list


def parse_reader(raw: str) -> list:
    match = re.search(r"<facts>\s*(.*?)\s*</facts>", raw, re.S)
    text = match.group(1) if match else raw[raw.find("["): raw.rfind("]") + 1]
    facts = _json(text)
    if not isinstance(facts, list):
        raise ValueError("the reading is not a JSON list")
    return facts


def assemble(sheet: dict, title: str, author: str, body: str) -> str:
    return (f"Title: {title}\nAuthor: {author}\nKind: {KIND_NAMES[sheet['kind']]}\n\n"
            + one_sentence_per_line(body))


# --- the registry of used images ------------------------------------------------------------------------


def load_registry() -> dict[str, list[str]]:
    """Spans of accepted texts by effect, plus the cue bank's examples (never to be copied)."""
    registry = {label: list(cues) for label, cues in load_cues().items()}
    if REGISTRY_FILE.exists():
        for row in json.loads(REGISTRY_FILE.read_text(encoding="utf-8")):
            registry.setdefault(row["effect"], []).append(row["span"])
    return registry


def register(sheet_id: str, cues: list[dict], registry: dict[str, list[str]]) -> None:
    rows = json.loads(REGISTRY_FILE.read_text(encoding="utf-8")) if REGISTRY_FILE.exists() else []
    rows = [r for r in rows if r["source"] != sheet_id]
    for cue in cues:
        rows.append({"source": sheet_id, "effect": cue["effect"], "span": cue["span"]})
        registry.setdefault(cue["effect"], []).append(cue["span"])
    REGISTRY_FILE.write_text("[\n" + ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows) + "\n]\n",
                             encoding="utf-8")


# --- one sheet ------------------------------------------------------------------------------------------


def seed(sheet_id: str, attempt: int, role: str) -> int:
    return zlib.crc32(f"{sheet_id}:{attempt}:{role}".encode())


def write_sheet(sheet: dict, writer, reader, registry: dict, attempts: int, log) -> bool:
    write_metadata(sheet)                     # what the source must imply, before any text exists
    expected, feedback = items(sheet), []
    for attempt in range(1, attempts + 1):
        record = {"sheet": sheet["id"], "attempt": attempt, "feedback": feedback}
        messages = [{"role": "system", "content": writer_system(sheet)},
                    {"role": "user", "content": writer_user(sheet, registry, feedback)}]
        answer = writer.complete(messages, seed(sheet["id"], attempt, "writer"))
        record.update(writer=answer.content, writer_seconds=answer.seconds, writer_usage=answer.usage)
        try:
            title, author, body, cues = parse_writer(answer.content)
        except ValueError as err:
            feedback = [str(err)]
        else:
            text = assemble(sheet, title, author, body)
            feedback = problems_text(text, sheet)
            feedback += [f"names not in the brief: {stray}" for stray in [stray_names(text, sheet)] if stray]
            feedback += check_cues(body, expected, cues, registry)
            if not feedback:
                reading = reader.complete([{"role": "system", "content": reader_system()},
                                           {"role": "user", "content": text}], seed(sheet["id"], attempt, "reader"))
                record.update(reader=reading.content, reader_seconds=reading.seconds)
                try:
                    feedback = compare(expected, parse_reader(reading.content))
                except (ValueError, json.JSONDecodeError) as err:
                    feedback = [f"(the reader's answer could not be parsed: {err}; try again)"]
            record["text"] = text
        record["problems"] = feedback
        log.write(json.dumps(record, ensure_ascii=False) + "\n")
        log.flush()
        print(f"  {sheet['id']} attempt {attempt}: " + ("accepted" if not feedback else f"{len(feedback)} problems"),
              flush=True)
        if not feedback:
            path_of(sheet["id"]).write_text(text, encoding="utf-8")
            register(sheet["id"], cues, registry)
            for path in failed_of(sheet["id"]):
                path.unlink(missing_ok=True)
            return True
    failed_text, failed_problems = failed_of(sheet["id"])
    failed_text.write_text(record.get("text", record["writer"]), encoding="utf-8")
    failed_problems.write_text(json.dumps(feedback, indent=2, ensure_ascii=False), encoding="utf-8")
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
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="rewrite texts that already pass")
    parser.add_argument("--writer-thinking", choices=("on", "off"), default="on")
    parser.add_argument("--reader-thinking", choices=("on", "off"), default="on")
    parser.add_argument("--reasoning-effort", default="low", help="Qwen3.8: low | medium | xhigh")
    parser.add_argument("--writer-max-tokens", type=int, default=32768, help="thinking included")
    parser.add_argument("--reader-max-tokens", type=int, default=24576, help="thinking included")
    parser.add_argument("--reader-temperature", type=float, default=0.0,
                        help="0: the reader decodes greedily, so a text's verdict does not depend on chance "
                             "(the writer keeps the model's recommended sampling)")
    parser.add_argument("--dry-run", action="store_true", help="print the first sheet's prompts and stop")
    args = parser.parse_args(argv)

    sheets = [s for s in select(args) if args.force or not done(s)]
    registry = load_registry()
    if args.dry_run:
        if not sheets:
            print("nothing to write")
            return 0
        print(writer_system(sheets[0]), "\n\n=== USER ===\n", writer_user(sheets[0], registry, []),
              "\n\n=== READER ===\n", reader_system(), sep="")
        return 0

    from LLM.client import ChatClient   # only needed with a server

    def client(thinking: str, max_tokens: int, temperature: float | None = None) -> ChatClient:
        return ChatClient(args.server, args.model, max_tokens, temperature=temperature, thinking=thinking == "on",
                          reasoning_effort=args.reasoning_effort, timeout=1800)

    writer = client(args.writer_thinking, args.writer_max_tokens)
    reader = client(args.reader_thinking, args.reader_max_tokens, args.reader_temperature)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        lock = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit(f"another run holds {LOCK_FILE} (two runs would share the image registry); delete it if stale")
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
                results[plant] = [write_sheet(s, writer, reader, registry, args.attempts, log) for s in todo]
            print(f"{plant}: {sum(results[plant])} accepted, {results[plant].count(False)} failed "
                  f"({(time.monotonic() - start) / 60:.0f} min so far)", flush=True)
    finally:
        LOCK_FILE.unlink(missing_ok=True)
    return 0 if all(all(r) for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
