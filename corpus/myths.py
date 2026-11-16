"""Layer 2 of the corpus pool: the myth pool (demo_spec.md, Sources).

Every catalogue fact gets one fixed wrong version per fallible kind (books never lie), drawn before any
text is written, so all the false sources of a kind tell the same myth. The kinds get different myths,
so false sources of different kinds disagree. A myth is never the truth.

    python -m corpus.myths          # writes content/myths.json
"""

import json
import random

from corpus.catalogue import CATALOGUE_FILE, CONTENT, SEED, SOIL_VALUES, load_plants
from environment.brewer import MODIFIERS, PLANTS, STAT_SETS

MYTHS_FILE = CONTENT / "myths.json"
FALLIBLE = ("transcript", "herbal", "pamphlet", "folk")
LABELS = tuple(MODIFIERS)
STATS = tuple(STAT_SETS)


def _labels(labels) -> list[str]:
    return sorted(labels, key=LABELS.index)


def candidates(fact: dict, table: dict) -> list:
    """Every wrong version of a fact that a myth may tell (one change from the truth)."""
    kind, value = fact["type"], fact.get("value")
    if kind == "alias":
        # a local confusion: a plant that grows in one of the true plant's places
        near = {p for members in table["groups"].values() if value in members for p in members}
        return [p for p in PLANTS if p in near and p != value]
    if kind == "group":
        # the plant is moved to a place it does not grow in (never denied where it does)
        plant = fact["plants"][0]
        return [{"group": g} for g, members in table["groups"].items() if plant not in members]
    if kind == "soil":
        return [v for v in SOIL_VALUES if v != value]
    if kind == "brew":
        return _brew_myths(value, len(fact["plants"]))
    if kind == "mix":
        return _mix_myths(fact["reveal"])
    raise ValueError(f"unknown fact type {kind}")


def _brew_myths(value: dict, size: int) -> list[dict]:
    stat, labels = value["stat"], value["labels"]
    if size == 2:                                                        # another label, or nothing
        return [{"stat": None, "labels": [other]} for other in LABELS if [other] != labels] + \
            ([{"stat": None, "labels": []}] if labels else [])
    out = []
    for i, label in enumerate(labels):                                   # swap or drop a label
        rest = labels[:i] + labels[i + 1:]
        out += [{"stat": stat, "labels": _labels(rest + [other])} for other in LABELS if other not in labels]
        out.append({"stat": stat, "labels": rest})
    if len(labels) < 3:                                                  # add a label
        out += [{"stat": stat, "labels": _labels(labels + [other])} for other in LABELS if other not in labels]
    out += [{"stat": other, "labels": labels} for other in STATS if other != stat]   # wrong or added stat
    if stat:
        out.append({"stat": None, "labels": labels})                     # deny the stat
    unique = []
    for myth in out:
        if myth != value and myth not in unique:
            unique.append(myth)
    return unique


def _mix_myths(reveal: dict) -> list[dict]:
    """A mix myth changes one revealed effect; the plants and how they are named stay true."""
    out = []
    for part, options in (("primary", STATS), ("secondary", LABELS), ("second", LABELS)):
        if reveal.get(part):
            out += [{**reveal, part: other} for other in options if other != reveal[part]]
    return out


def myth_pool(facts: list[dict], table: dict, seed: int = SEED) -> dict[str, dict[str, object]]:
    pool = {}
    for fact in facts:
        options = candidates(fact, table)
        rng = random.Random(f"{seed}:{fact['id']}")
        chosen = rng.sample(options, len(FALLIBLE)) if len(options) >= len(FALLIBLE) else \
            [rng.choice(options) for _ in FALLIBLE]
        pool[fact["id"]] = dict(zip(FALLIBLE, chosen))
    return pool


def load_catalogue() -> list[dict]:
    return json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))


def dump(pool: dict) -> str:
    """One fact per line."""
    return "{\n" + ",\n".join(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                              for k, v in pool.items()) + "\n}\n"


if __name__ == "__main__":
    pool = myth_pool(load_catalogue(), load_plants())
    MYTHS_FILE.write_text(dump(pool), encoding="utf-8")
    print(f"{len(pool)} facts x {len(FALLIBLE)} kinds -> {MYTHS_FILE}")
