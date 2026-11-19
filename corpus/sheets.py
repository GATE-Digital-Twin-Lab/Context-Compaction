"""Layer 3 of the corpus pool: the source sheets (demo_spec.md, Sources).

A sheet is the hidden answer key of one source: its kind, focus plant, target length and padding, and
the facts it states, each with its truth and what it tells (the truth, or its kind's myth from layer 2).
Texts (layer 4) are written from the sheets and checked against them.

    python -m corpus.sheets         # writes content/sheets.json
"""

import json
import random

from corpus.catalogue import CONTENT, SEED, about, load_plants, revealable
from corpus.myths import LABELS, MYTHS_FILE, STATS, load_catalogue
from corpus.trials import ledgers
from environment.brewer import PLANTS

SHEETS_FILE = CONTENT / "sheets.json"
KINDS = ("book", "transcript", "herbal", "pamphlet", "folk")

# per plant: how many sources, fact correct, padding (share of the text), length in words, share of
# facts told vaguely, and how a co-ingredient of a brew is named (official name, alias, group)
SPEC = {
    "book":       {"count": 1,  "rate": 1.0, "padding": 0.20, "words": (1200, 1800), "vague": 0.0,
                   "naming": (1.0, 0.0, 0.0)},
    "transcript": {"count": 8,  "rate": 0.8, "padding": 0.20, "words": (300, 500),   "vague": 0.0,
                   "naming": (1.0, 0.0, 0.0)},
    "herbal":     {"count": 5,  "rate": 0.7, "padding": 0.75, "words": (600, 900),   "vague": 0.3,
                   "naming": (0.4, 0.4, 0.2)},
    "pamphlet":   {"count": 15, "rate": 0.6, "padding": 0.40, "words": (100, 200),   "vague": 0.2,
                   "naming": (0.4, 0.25, 0.35)},
    "folk":       {"count": 15, "rate": 0.4, "padding": 0.55, "words": (150, 300),   "vague": 0.7,
                   "naming": (0.2, 0.4, 0.4)},
}
BOOK = {"alias": 3, "group": 3, "soil": 3, "pair": 7, "triple": 7, "mix": 2}    # 25 facts
TRANSCRIPT_FACTS = 5                                                            # brews or mixes
HERBAL_FACTS = 4                                                                # aliases, groups, soils
SHORT_FACTS = (1, 3)                                                            # pamphlets, folk tales
GUARANTEED = ("soil", "brew", "mix")       # in the pool, each has a true source naming its plants


def _type(fact: dict) -> str:
    if fact["type"] == "brew":
        return "pair" if len(fact["plants"]) == 2 else "triple"
    return fact["type"]


class Deck:
    """A shuffled cycle of rows: each source of a kind takes the next distinct rows, so the rows of a
    plant are covered evenly before any repeats."""

    def __init__(self, rows: list[dict], rng: random.Random):
        self.rows, self.rng, self.queue = rows, rng, []

    def draw(self, k: int) -> list[dict]:
        out, skipped = [], []
        while len(out) < k:
            if not self.queue:
                self.queue = self.rng.sample(self.rows, len(self.rows))
            row = self.queue.pop(0)
            (skipped if any(r["id"] == row["id"] for r in out) else out).append(row)
        self.queue = skipped + self.queue
        return out


# --- one stated fact ----------------------------------------------------------------------------


def _refs(fact: dict, focus: str, kind: str, table: dict, rng: random.Random) -> list[dict]:
    """How a brew names its co-ingredients (the focus plant is always named)."""
    refs = []
    for plant in fact["plants"]:
        if plant == focus:
            continue
        how = rng.choices(("name", "alias", "group"), SPEC[kind]["naming"])[0]
        if how == "alias":
            refs.append({"plant": plant, "alias": rng.choice(table["aliases"][plant])})
        elif how == "group":
            refs.append({"plant": plant, "group": rng.choice([g for g, m in table["groups"].items() if plant in m])})
        else:
            refs.append({"plant": plant})
    return refs


def truth(fact: dict):
    """What a true source tells."""
    if fact["type"] == "group":
        return {"group": fact["group"]}
    if fact["type"] == "mix":
        return fact["reveal"]
    return fact["value"]


def _state(fact: dict, focus: str, kind: str, table: dict, rng: random.Random) -> dict:
    spec = SPEC[kind]
    entry = {"fact": fact["id"], "type": _type(fact), "true": rng.random() < spec["rate"],
             "vague": rng.random() < spec["vague"]}
    if fact["type"] == "brew":
        entry["refs"] = _refs(fact, focus, kind, table, rng)
    elif fact["type"] == "mix":
        entry["refs"] = fact["second"].get("refs", [])
    return entry


def _more(mix: dict, rng: random.Random, rate: float, table: dict) -> dict | None:
    """Something more about a mix than its catalogue row reveals: another effect a drinker notices (the
    mix's, or the second brew's own), or which plant a group reference means. Drawn at the transcript's
    rate; a false one tells another effect, or another plant of the group."""
    reveal = mix["reveal"]
    shown = {reveal.get("primary"), reveal.get("second"), *(reveal.get("secondary") or [])}
    options = []
    primaries, secondaries = revealable(mix["plants"])
    options += [("effect", e) for e in primaries + secondaries if e not in shown]
    if mix["kind"] == "2+2" and mix["reveal"].get("second") is None:
        options += [("second", e) for e in revealable(mix["second"]["plants"])[1]]
    options += [("plant", ref) for ref in mix["second"].get("refs", []) if "group" in ref]
    if not options:
        return None
    what, value = rng.choice(options)
    true = rng.random() < rate
    entry = {"fact": f"more:{mix['id']}", "type": "more", "of": mix["id"], "true": true, "vague": False}
    if what == "plant":
        told = value["plant"]
        if not true:
            told = rng.choice([p for p in table["groups"][value["group"]] if p != value["plant"]])
        entry.update({"what": "plant", "group": value["group"], "value": value["plant"], "told": told})
        return entry
    actual = primaries + secondaries if what == "effect" else revealable(mix["second"]["plants"])[1]
    told = value if true else rng.choice([e for e in STATS + LABELS if e not in actual])
    entry.update({"what": what, "value": value, "told": told})
    return entry



# --- the sheets ---------------------------------------------------------------------------------


def _facts(kind: str, focus: str, rows: list[dict], decks: dict, i: int, extra: dict) -> list[dict]:
    """The catalogue rows one source states."""
    if kind == "book":
        rng = decks["book"]
        return [f for t, n in BOOK.items() for f in rng.sample([r for r in rows if _type(r) == t], n)]
    if kind == "transcript":
        return decks["transcript"].draw(TRANSCRIPT_FACTS)
    if kind == "herbal":
        out = decks["herbal"].draw(HERBAL_FACTS)
        return out + (decks["herbal_brew"].draw(1) if i == extra["herbal"] else [])
    return decks[kind].draw(decks["rng"].randint(*SHORT_FACTS))


def plant_sheets(focus: str, facts: list[dict], myths: dict, table: dict, seed: int = SEED) -> list[dict]:
    rows = about(focus, facts)
    rng = random.Random(f"{seed}:sheets:{focus}")
    brews_mixes = [r for r in rows if r["type"] in ("brew", "mix")]
    names = [r for r in rows if r["type"] in ("alias", "group", "soil")]
    decks = {"book": rng, "rng": rng,
             "transcript": Deck(brews_mixes, rng),
             "herbal": Deck(names, rng),
             "herbal_brew": Deck([r for r in rows if r["type"] == "brew"], rng),
             "pamphlet": Deck(rows, rng), "folk": Deck(rows, rng)}
    extra = {"herbal": rng.randrange(SPEC["herbal"]["count"]),
             "transcript": rng.randrange(SPEC["transcript"]["count"]),
             "transcript_what": rng.choice(("alias", "group", "more"))}
    sheets = []
    for kind in KINDS:
        spec = SPEC[kind]
        for i in range(spec["count"]):
            chosen = _facts(kind, focus, rows, decks, i, extra)
            stated = [_state(f, focus, kind, table, rng) for f in chosen]
            if kind == "transcript" and i == extra["transcript"]:
                stated.append(_transcript_extra(focus, chosen, rows, extra["transcript_what"], rng, spec["rate"],
                                                table))
            sheets.append({"id": f"{kind}:{focus}:{i + 1:02d}", "kind": kind, "focus": focus,
                           "words": rng.randint(*spec["words"]), "padding": spec["padding"], "facts": stated})
    return sheets


def _transcript_extra(focus, chosen, rows, what, rng, rate, table) -> dict:
    """The one transcript of a plant with something extra: an alias, a group, or more about a mix."""
    mixes = [f for f in chosen if f["type"] == "mix"]
    if what == "more":
        for mix in rng.sample(mixes, len(mixes)):
            more = _more(mix, rng, rate, table)
            if more:
                return more
        what = rng.choice(("alias", "group"))
    fact = rng.choice([r for r in rows if r["type"] == what])
    return {**_state(fact, focus, "transcript", table, rng), "extra": True}


def _fill(sheets: list[dict], facts: dict, myths: dict) -> None:
    """What each stated fact tells: the truth, or its kind's myth."""
    for sheet in sheets:
        for entry in sheet["facts"]:
            if entry["type"] == "more":
                continue
            fact = facts[entry["fact"]]
            entry["told"] = truth(fact) if entry["true"] else myths[fact["id"]][sheet["kind"]]


def _keep_references(sheets: list[dict]) -> int:
    """A text never states a false alias and also uses that alias: such an alias fact is told true."""
    forced = 0
    for sheet in sheets:
        used = {ref["alias"] for e in sheet["facts"] for ref in e.get("refs", []) if "alias" in ref}
        for entry in sheet["facts"]:
            if entry["type"] == "alias" and not entry["true"] and entry["fact"].split(":", 1)[1] in used:
                entry["true"], forced = True, forced + 1
    return forced


def _names_plants(entry: dict) -> bool:
    """A brew mention counts only if no co-ingredient is named by a group (a mix's references are part
    of its catalogue row, so any mention of it counts)."""
    return entry["type"] == "mix" or all("group" not in ref for ref in entry.get("refs", []))


def _guarantee(sheets: list[dict], facts: dict) -> int:
    """Every soil hint and brew gets a true source in the pool that names its plants (by name or alias),
    and every mix a true source: if it has none, its mention in the most reliable kind is made true."""
    mentions: dict[str, list[tuple[int, dict]]] = {}
    for sheet in sheets:
        for entry in sheet["facts"]:
            if facts.get(entry["fact"], {}).get("type") in GUARANTEED and _names_plants(entry):
                mentions.setdefault(entry["fact"], []).append((KINDS.index(sheet["kind"]), entry))
    repaired = 0
    for fid, fact in facts.items():
        if fact["type"] not in GUARANTEED:
            continue
        found = sorted(mentions.get(fid, []), key=lambda m: m[0])
        assert found, f"{fid} is never stated with its plants named"
        if not any(e["true"] for _, e in found):
            found[0][1]["true"], repaired = True, repaired + 1
    return repaired


def build(facts: list[dict] | None = None, myths: dict | None = None, table: dict | None = None,
          seed: int = SEED) -> tuple[list[dict], dict]:
    facts = facts or load_catalogue()
    myths = myths or json.loads(MYTHS_FILE.read_text(encoding="utf-8"))
    table = table or load_plants()
    sheets = [s for plant in PLANTS for s in plant_sheets(plant, facts, myths, table, seed)]
    by_id = {f["id"]: f for f in facts}
    stats = {"forced_alias": _keep_references(sheets), "repaired": _guarantee(sheets, by_id)}
    _fill(sheets, by_id, myths)
    return sheets + ledgers(seed), stats            # one trial ledger per stat (corpus/trials.py)


def dump(sheets: list[dict]) -> str:
    """One sheet per line."""
    return "[\n" + ",\n".join("  " + json.dumps(s, ensure_ascii=False) for s in sheets) + "\n]\n"


if __name__ == "__main__":
    sheets, stats = build()
    SHEETS_FILE.write_text(dump(sheets), encoding="utf-8")
    print(f"{len(sheets)} sheets, {sum(len(s['facts']) for s in sheets)} stated facts, {stats} -> {SHEETS_FILE}")
