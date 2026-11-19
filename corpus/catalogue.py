"""Layer 1 of the corpus pool: the catalogue of true facts (demo_spec.md, Sources).

One row per possible fact, with its true value and the plants it involves; a source with focus plant X
draws its facts from the rows that involve X (for mixes: the rows whose focus is X). Aliases and groups
come from content/plants.json, the rest from the game rules (brewer, soils). Mixes are a balanced
selection, not every possible mix (see mixes()).

    python -m corpus.catalogue      # writes content/catalogue.json
"""

import json
import random
from itertools import combinations
from pathlib import Path

from environment.brewer import MODIFIERS, PLANTS, STAT_SETS, net_modifier, secondary_labels
from environment.soils import SOIL_TABLE, SOILS

CONTENT = Path(__file__).parent.parent / "content"
PLANTS_FILE = CONTENT / "plants.json"
CATALOGUE_FILE = CONTENT / "catalogue.json"

SOIL_VALUES = ("dies", "sometimes fails", "fast", "slow", "ordinary")
SEED = 17
STYLES = ("alias+alias", "alias+group", "group+group")      # how a 2+2 mix names its second brew


def load_plants() -> dict:
    return json.loads(PLANTS_FILE.read_text(encoding="utf-8"))


def soil_value(plant: str, soil: str) -> str:
    time, chance = SOIL_TABLE[plant][soil]
    if chance == 0:
        return "dies"
    if chance < 100:
        return "sometimes fails"
    return "fast" if time <= 3 else "slow" if time >= 5 else "ordinary"


def noticed(labels) -> list[str]:
    """What a drinker notices of a potion's secondary labels: every distinct label when they all pull the
    same way (sweet and fragrant: both), and nothing when positive and negative ones meet, since they
    cancel and the potion tastes like plain water. Two pairs with the same label are noticed once."""
    labels = list(labels)
    if any(MODIFIERS[lab] > 0 for lab in labels) and any(MODIFIERS[lab] < 0 for lab in labels):
        return []
    return sorted(set(labels), key=list(MODIFIERS).index)


def brew_value(plants) -> dict:
    """The stat whose set is these plants (direction left to experiment), and the labels a drinker notices."""
    stat = next((s for s, members in STAT_SETS.items() if set(members) <= set(plants)), None)
    return {"stat": stat, "labels": noticed(secondary_labels(plants))}


def _ordered(plants) -> list[str]:
    return sorted(plants, key=PLANTS.index)


# --- mixes ---------------------------------------------------------------------------------------
# Sources never give counts, so a mix is judged on its plants only: a primary "acts on S" when S's set
# is present (direction left to experiment, as for brews), and the secondary labels depend on presence.


def mix_value(plants) -> dict:
    """Every stat whose set the plants contain, the labels, and whether it can be drunk."""
    present = set(plants)
    labels = list(secondary_labels(present))
    return {"stats": [s for s, members in STAT_SETS.items() if set(members) <= present], "labels": labels,
            "drinkable": net_modifier(labels) > -100}


def revealable(plants) -> tuple[list[str], list[str]]:
    """What a drinker could tell of a mix: the stats it acts on, and the labels noticed (see noticed():
    all of them when they pull the same way, none when they cancel). An undrinkable mix shows no
    primary, only its poison."""
    value = mix_value(plants)
    labels = noticed(value["labels"])
    return (value["stats"] if value["drinkable"] else []), labels


def _reaches_w(plants) -> bool:
    return "W" in revealable(plants)[0]


def _usable(plants) -> bool:
    """Something to reveal, and not W (W mixes are chosen on purpose)."""
    primaries, secondaries = revealable(plants)
    return bool(primaries or secondaries) and "W" not in primaries


def _ref(plant: str, how: str, table: dict, rng: random.Random) -> dict:
    if how == "alias":
        return {"plant": plant, "alias": rng.choice(table["aliases"][plant])}
    return {"plant": plant, "group": rng.choice([g for g, m in table["groups"].items() if plant in m])}


def _mix(focus: str, named: list[str], second: dict, reveal: dict) -> dict:
    kind = "2+2" if len(second["plants"]) == 2 else "3+2"
    plants = _ordered(set(named) | set(second["plants"]))
    return {"id": f"mix:{focus}:" + "+".join(_ordered(named)) + "|" + "+".join(second["plants"]), "type": "mix",
            "focus": focus, "kind": kind, "plants": plants, "named": _ordered(named), "second": second,
            "reveal": reveal, "value": mix_value(plants)}


def mixes(table: dict, seed: int = SEED) -> list[dict]:
    """Six mixes per focus plant X. The named brew {X, y} is told by official names, without its effect.
    - 3 of 2+2, one per style: the second brew {u, v} (any two plants, X included, not the named brew)
      is named by two aliases, an alias and a group, or two groups; when a group is used, the second
      brew's own effect is revealed (if it has one). One effect of the mix is revealed.
    - 3 of 3+2: the second brew is a whole group (any group). One stat (if any) and one acting
      secondary (if any) of the mix are revealed. One of them reaches W, and W is the stat revealed;
      no other mix reaches W.
    Every mix has something to reveal."""
    rows = []
    for x in PLANTS:
        rng = random.Random(f"{seed}:{x}")
        named = [[x, y] for y in PLANTS if y != x]
        used = set()
        for style in STYLES:
            pool = [(n, list(pair)) for n in named for pair in combinations(PLANTS, 2)
                    if set(pair) != set(n) and (tuple(n), pair) not in used and _usable(set(n) | set(pair))]
            n, pair = rng.choice(pool)
            used.add((tuple(n), tuple(pair)))
            hows = {"alias+alias": ["alias", "alias"], "group+group": ["group", "group"],
                    "alias+group": rng.sample(["alias", "group"], 2)}[style]
            refs = [_ref(p, how, table, rng) for p, how in zip(pair, hows)]
            primaries, secondaries = revealable(set(n) | set(pair))
            shown = rng.choice(primaries + secondaries)
            own = revealable(pair)[1] if "group" in style else []
            rows.append(_mix(x, n, {"plants": _ordered(pair), "refs": refs, "style": style}, {
                "second": rng.choice(own) if own else None,
                "primary": shown if shown in primaries else None,
                "secondary": secondaries if shown in secondaries else None,     # every label noticed
            }))
        three = [(n, g) for n in named for g in table["groups"]]
        w = [m for m in three if _reaches_w(set(m[0]) | set(table["groups"][m[1]]))]
        others = [m for m in three if _usable(set(m[0]) | set(table["groups"][m[1]]))]
        for i, (n, g) in enumerate([rng.choice(w)] + rng.sample(others, 2)):
            primaries, secondaries = revealable(set(n) | set(table["groups"][g]))
            rows.append(_mix(x, n, {"plants": _ordered(table["groups"][g]), "group": g}, {
                "primary": "W" if i == 0 else rng.choice(primaries) if primaries else None,
                "secondary": secondaries if secondaries and rng.choice(secondaries) else None,   # every label
            }))
    return rows


# --- the catalogue -------------------------------------------------------------------------------


def catalogue(table: dict | None = None) -> list[dict]:
    table = table or load_plants()
    facts = []
    for plant in PLANTS:
        for alias in table["aliases"][plant]:
            facts.append({"id": f"alias:{alias}", "type": "alias", "plants": [plant], "alias": alias, "value": plant})
    for group, members in table["groups"].items():
        for plant in sorted(members, key=PLANTS.index):
            facts.append({"id": f"group:{group}:{plant}", "type": "group", "plants": [plant], "group": group,
                          "value": True})
    for plant in PLANTS:
        for soil in SOILS:
            facts.append({"id": f"soil:{plant}:{soil}", "type": "soil", "plants": [plant], "soil": soil,
                          "value": soil_value(plant, soil)})
    for size in (2, 3):
        for plants in combinations(PLANTS, size):
            facts.append({"id": "brew:" + "+".join(plants), "type": "brew", "plants": list(plants),
                          "value": brew_value(plants)})
    return facts + mixes(table)


def about(plant: str, facts: list[dict]) -> list[dict]:
    """The rows a source with this focus plant draws from (a mix only through its focus plant)."""
    return [f for f in facts if plant in f["plants"] and f.get("focus", plant) == plant]


def dump(facts: list[dict]) -> str:
    """One fact per line, so the file reads as a table."""
    return "[\n" + ",\n".join("  " + json.dumps(f, ensure_ascii=False) for f in facts) + "\n]\n"


if __name__ == "__main__":
    facts = catalogue()
    CATALOGUE_FILE.write_text(dump(facts), encoding="utf-8")
    print(f"{len(facts)} facts -> {CATALOGUE_FILE}")
