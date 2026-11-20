"""Layer 4 without the model: what a text must say (the writer's brief), what a blind reader of it should
find, and the checks that need the sheet (stray names, cue spans and their novelty). The model calls
are in corpus/write.py.

A sheet's facts become numbered items F1, F2, ... Each item has a key (what the claim is about, with
plants as the text names them) and a value (what the claim says), in the same form a blind reading is
normalised to, so a reading is checked by comparing keys and values.
"""

import json
import re
from functools import lru_cache

from corpus.catalogue import load_plants
from corpus.glossary import load_glossary
from corpus.myths import load_catalogue
from environment.brewer import PLANTS

SOIL_TOLD = {
    "dies": "it dies there: it never survives",
    "sometimes fails": "it sometimes fails there: some plantings die, others grow",
    "fast": "it grows quickly there",
    "slow": "it grows slowly there",
    "ordinary": "it grows at an ordinary pace there, neither quick nor slow",
}
VAGUE = (" Tell this one vaguely (hearsay, a shaky memory, a doubt), but a careful reader must still be able"
         " to make it out.")
@lru_cache
def _facts() -> dict[str, dict]:
    return {f["id"]: f for f in load_catalogue()}


@lru_cache
def _table() -> dict:
    return load_plants()


def norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").strip().strip("\"'").strip().lower()
    return re.sub(r"\s+", " ", text)


def place_key(place: str) -> str:
    place = norm(place)
    return place[4:] if place.startswith("the ") else place


def stat_name(stat: str) -> str:
    return load_glossary()["stats"][stat]["name"]


# --- plants as a text names them ------------------------------------------------------------------


def ref_key(ref: dict) -> tuple[str, str]:
    if "alias" in ref:
        return ("alias", norm(ref["alias"]))
    if "group" in ref:
        return ("group", place_key(ref["group"]))
    return ("plant", ref["plant"])


def ref_words(ref: dict) -> str:
    if "alias" in ref:
        return f'"{ref["alias"]}"'
    if "group" in ref:
        return f'"a plant of {ref["group"]}"'
    return ref["plant"]


def ref_rule(ref: dict) -> str:
    if "alias" in ref:
        return f' "{ref["alias"]}" is a folk name: use exactly that name and never say which plant it is.'
    if "group" in ref:
        return f' Name that plant only as a plant of {ref["group"]}, never which plant it is.'
    return ""


def parse_ref(text: str) -> tuple[str, str]:
    """A plant as a reader wrote it: an official name, a folk name, a plant of a place, or all of a place."""
    n = norm(text)
    if n in PLANTS:
        return ("plant", n)
    for aliases in _table()["aliases"].values():
        if any(norm(a) == n for a in aliases):
            return ("alias", n)
    for group in _table()["groups"]:
        if place_key(group) in n:
            whole = any(w in n.split() for w in ("all", "whole", "three", "every"))
            return ("whole" if whole else "group", place_key(group))
    return ("unknown", n)


def _effects(stat, labels) -> list[str]:
    return sorted(([stat] if stat else []) + list(labels))


def _effect_words(effects: list[str]) -> str:
    if not effects:
        return ("nothing happens at all: it tastes, smells and looks like plain water, and no drinker "
                "changes")
    words = [f"it acts on {stat_name(e)} ({e}): a drinker gains or loses in it" if e in "SDVIW" else e
             for e in effects]
    return "; ".join(words)


# --- the items of a sheet -------------------------------------------------------------------------


def items(sheet: dict) -> list[dict]:
    """The claims a text must make: key, value, the writer's brief, and the effects that need a cue."""
    facts, focus = _facts(), sheet["focus"]
    more = {e["of"]: e for e in sheet["facts"] if e["type"] == "more"}
    out = []
    for entry in sheet["facts"]:
        if entry["type"] == "more":
            continue
        fact, told = facts.get(entry["fact"], {}), entry["told"]
        item = {"fact": entry["fact"], "type": entry["type"], "cues": []}
        if entry["type"] == "alias":
            item.update(key=("alias", norm(fact["alias"])), value=told,
                        brief=f'Say that "{fact["alias"]}" is a name for {told}.')
        elif entry["type"] == "group":
            item.update(key=("group", focus, place_key(told["group"])), value=True,
                        brief=f"Say that {focus} grows wild at {told['group']}.")
        elif entry["type"] == "soil":
            item.update(key=("soil", focus, fact["soil"]), value=told,
                        brief=f"Say how {focus} grows in {fact['soil']} earth: {SOIL_TOLD[told]}.")
        elif entry["type"] in ("pair", "triple"):
            effects = _effects(told["stat"], told["labels"])
            names = [focus] + [ref_words(r) for r in entry["refs"]]
            item.update(key=("brew", tuple(sorted([("plant", focus)] + [ref_key(r) for r in entry["refs"]]))),
                        value=effects, cues=effects,
                        brief=f"A brew of {', '.join(names[:-1])} and {names[-1]} together (never any amounts): "
                              f"{_effect_words(effects)}." + "".join(ref_rule(r) for r in entry["refs"]))
        elif entry["type"] == "mix":
            item.update(_mix_item(fact, told, more.get(fact["id"])))
        elif entry["type"] == "trial":
            item.update(_trial_item(entry, focus))
        item["brief"] += VAGUE if entry["vague"] else ""
        out.append(item)
        extra = more.get(entry["fact"])
        if extra and extra["what"] == "plant":
            out.append({"fact": extra["fact"], "type": "identity", "cues": [],
                        "key": ("identity", ("group", place_key(extra["group"]))), "value": extra["told"],
                        "brief": f"In the mix above, also say that its plant of {extra['group']} was {extra['told']}."})
    for i, item in enumerate(out, 1):
        item["n"] = f"F{i}"
    return out


def _mix_item(fact: dict, told: dict, extra: dict | None) -> dict:
    first = fact["named"]
    second = fact["second"]
    if "group" in second:                                                    # 3 + 2: a whole group
        second_key, second_words, rules = (("whole", place_key(second["group"])),), \
            f"all three plants of {second['group']}", ""
    else:
        second_key = tuple(sorted(ref_key(r) for r in second["refs"]))
        second_words = " and ".join(ref_words(r) for r in second["refs"])
        rules = "".join(ref_rule(r) for r in second["refs"])
    alone = [told["second"]] if told.get("second") else []
    mixed = ([told["primary"]] if told.get("primary") else []) + list(told.get("secondary") or [])
    if extra and extra["what"] == "second":
        alone.append(extra["told"])
    if extra and extra["what"] == "effect":
        mixed.append(extra["told"])
    alone, mixed = sorted(alone), sorted(mixed)
    brief = (f"Two brews are poured together into one. The first brew: {first[0]} and {first[1]}; never say "
             f"what it does on its own. The second brew: {second_words}." + rules +
             (f" The second brew on its own: {_effect_words(alone)}." if alone else "") +
             f" The mixed potion: {_effect_words(mixed)}. Say nothing else about what either brew or the mix does.")
    return {"key": ("mix", tuple(sorted(("plant", p) for p in first)), second_key),
            "value": {"second_alone": alone, "mixed": mixed}, "cues": sorted(set(alone + mixed)), "brief": brief}


def trial_key(base, added) -> tuple:
    """A trial's key: the drinker's brew, and every brew poured into it (plants by official name)."""
    return ("trial", tuple(sorted(("plant", p) for p in base)),
            tuple(sorted(tuple(sorted(("plant", p) for p in brew)) for brew in added)))


def trial_effects(told: dict) -> list[str]:
    return sorted(([told["stat"]] if told["stat"] else []) + list(told["noticed"]))


def _trial_item(entry: dict, stat: str) -> dict:
    """A trial is given to the writer as data to wrap in prose: what was drunk, the two counts of work, and
    what was noticed. The hidden plant counts and the percentage are left out on purpose: the text must
    never show them, and the two counts already carry the percentage."""
    told = entry["told"]
    base = list(entry["base"])
    poured = [list(brew) for brew in entry["added"]]
    noticed_words = "; ".join(told["noticed"]) or "nothing: it tasted, smelled and looked like plain water"
    text = ("A trial (one ledger entry: a named drinker; wrap this data in your own words): "
            f"drank: a brew of {', '.join(base[:-1])} and {base[-1]} together (never any amounts) | "
            + "".join(f"poured into it: a brew of {' and '.join(brew)} | " for brew in poured) +
            f"work counted: a task that shows {stat_name(stat)}, in countable things | "
            f"before drinking: {told['before']} | after drinking: {told['after']}"
            + (" (no change at all)" if told["before"] == told["after"] else "") + " | "
            f"noticed while drinking: {noticed_words}. Give both counts exactly, never as a share or a percentage; "
            "show each label noticed through its own image, in the potion itself, never as a change in the drinker.")
    return {"key": trial_key(base, poured), "value": {"before": told["before"], "after": told["after"],
                                                       "effects": trial_effects(told)},
            "cues": list(told["noticed"]), "brief": text}


def brief(sheet: dict) -> str:
    return "\n".join(f"{item['n']}. {item['brief']}" for item in items(sheet))


# --- the blind reading ------------------------------------------------------------------------------


def read_key_value(fact: dict):
    """A reader's claim in the items' form; None if it is not a claim of a known type."""
    kind = fact.get("type")
    try:
        if kind == "alias":
            return ("alias", norm(fact["name"])), norm(fact["plant"])
        if kind == "place":
            return ("group", norm(fact["plant"]), place_key(fact["place"])), True
        if kind == "soil":
            return ("soil", norm(fact["plant"]), norm(fact["earth"])), norm(fact["growth"])
        if kind == "brew":
            return ("brew", tuple(sorted(parse_ref(p) for p in fact["plants"]))), sorted(fact.get("effects", []))
        if kind == "mix":
            return (("mix", tuple(sorted(parse_ref(p) for p in fact["first"])),
                     tuple(sorted(parse_ref(p) for p in fact["second"]))),
                    {"second_alone": sorted(fact.get("second_alone") or []), "mixed": sorted(fact.get("mixed") or [])})
        if kind == "identity":
            return ("identity", parse_ref(fact["ref"])), norm(fact["plant"])
        if kind == "trial":
            key = ("trial", tuple(sorted(parse_ref(p) for p in fact["plants"])),
                   tuple(sorted(tuple(sorted(parse_ref(p) for p in brew)) for brew in fact.get("added") or [])))
            after = fact["after"]
            return key, {"before": int(fact["before"]), "after": None if after is None else int(after),
                         "effects": sorted(fact.get("effects", []))}
    except (KeyError, TypeError, AttributeError, ValueError):
        return None
    return None


def compare(expected: list[dict], reading: list[dict]) -> list[str]:
    """Every item found with its value, and nothing else found."""
    found = []
    for fact in reading:
        kv = read_key_value(fact)
        found.append((kv, fact))
    problems, used = [], set()
    for item in expected:
        matches = [i for i, (kv, _) in enumerate(found) if kv and kv[0] == item["key"]]
        if not matches:
            problems.append(f"{item['n']} not found by the reader ({item['brief'][:90]})")
            continue
        used.update(matches)
        values = [found[i][0][1] for i in matches]
        if item["value"] not in values:
            problems.append(f"{item['n']}: the reader found {json.dumps(values[0])}, it should be "
                            f"{json.dumps(item['value'])}")
    for i, (kv, fact) in enumerate(found):
        if i not in used:
            problems.append(f"the reader found a claim that is not in the brief: {json.dumps(fact, ensure_ascii=False)}")
    return problems


# --- names a text may use ---------------------------------------------------------------------------


def allowed_names(sheet: dict) -> dict[str, set[str]]:
    facts, focus = _facts(), sheet["focus"]
    plants, aliases, places = {focus}, set(), set()

    def add_ref(ref):
        if "alias" in ref:
            aliases.add(norm(ref["alias"]))
        elif "group" in ref:
            places.add(place_key(ref["group"]))
        else:
            plants.add(ref["plant"])

    for entry in sheet["facts"]:
        if entry["type"] == "more":
            if entry["what"] == "plant":
                plants.add(entry["told"])
                places.add(place_key(entry["group"]))
            continue
        if entry["type"] == "trial":
            plants.update(entry["base"])
            plants.update(p for brew in entry["added"] for p in brew)
            continue
        fact = facts[entry["fact"]]
        for ref in entry.get("refs", []):
            add_ref(ref)
        if entry["type"] == "alias":
            aliases.add(norm(fact["alias"]))
            plants.add(entry["told"])
        elif entry["type"] == "group":
            places.add(place_key(entry["told"]["group"]))
        elif entry["type"] == "mix":
            plants.update(fact["named"])
            if "group" in fact["second"]:
                places.add(place_key(fact["second"]["group"]))
    return {"plants": plants, "aliases": aliases, "places": places}


def _mentions(text: str, name: str) -> bool:
    return re.search(r"(?<![\w'])" + re.escape(name) + r"(?![\w'])", text) is not None


def stray_names(text: str, sheet: dict) -> list[str]:
    """Plants, folk names and places the text mentions although its sheet does not use them."""
    flat = norm(text)
    allowed = allowed_names(sheet)
    out = [p for p in PLANTS if p not in allowed["plants"] and _mentions(flat, p)]
    out += [a for aliases in _table()["aliases"].values() for a in aliases
            if norm(a) not in allowed["aliases"] and _mentions(flat, norm(a))]
    out += [g for g in _table()["groups"] if place_key(g) not in allowed["places"] and _mentions(flat, place_key(g))]
    return out
