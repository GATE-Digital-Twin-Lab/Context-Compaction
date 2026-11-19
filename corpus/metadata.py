"""The metadata of every source: what it implies, in plain words, before and beside its text.

Each source has a folder content/texts/<id>/ with metadata.json, written from the sheet before the text is
generated, and the text itself (<id>.txt) once one passes. The metadata lists every claim the text makes
(numbered as in the writer's brief), what the agent should learn from the true ones, and for every false
claim the truth and what is wrong with it. It also shows what lies behind each claim (which plants a folk
name or a place stands for, the pairs that give the labels, a trial's hidden counts), for review only.

    python -m corpus.metadata       # writes metadata.json for every sheet
"""

import json
import sys

from corpus.briefs import items, ref_words, stat_name
from corpus.catalogue import load_plants, noticed
from corpus.myths import load_catalogue
from corpus.sheets import SHEETS_FILE, truth
from corpus.texts import KIND_NAMES, folder_of
from corpus.trials import signed
from environment.brewer import MODIFIERS, SECONDARY_PAIRS, net_modifier, secondary_labels


def _effects(effects) -> str:
    if not effects:
        return "nothing: it tastes, smells and looks like plain water, and no drinker changes"
    return "; ".join(f"acts on {stat_name(e)} ({e})" if e in "SDVIW" else e for e in effects)


def _brew_effects(value: dict) -> list[str]:
    return ([value["stat"]] if value.get("stat") else []) + list(value.get("labels", []))


def _pairs(plants) -> list[str]:
    """The pairs among some plants that give a label, with the label's modifier."""
    present = set(plants)
    return [f"{' + '.join(sorted(pair))} -> {label} ({MODIFIERS[label]:+d}%)"
            for pair, label in SECONDARY_PAIRS.items() if pair <= present]


def _names(refs: list[dict]) -> dict[str, str]:
    return {ref_words(r).strip('"'): r["plant"] for r in refs if "alias" in r or "group" in r}


def _diff(told: list[str], true: list[str]) -> str:
    added, dropped = [x for x in told if x not in true], [x for x in true if x not in told]
    parts = []
    if added and dropped:
        parts.append(f"says {', '.join(added)} instead of {', '.join(dropped)}")
    elif added:
        parts.append(f"adds {', '.join(added)}, which is not there")
    elif dropped:
        parts.append(f"leaves out {', '.join(dropped)}")
    return "; ".join(parts)


def _brew_issue(told: dict, value: dict) -> str:
    parts = []
    if told["stat"] != value["stat"]:
        if told["stat"] and value["stat"]:
            parts.append(f"names {stat_name(told['stat'])} ({told['stat']}) instead of {stat_name(value['stat'])} "
                         f"({value['stat']})")
        elif told["stat"]:
            parts.append(f"claims it acts on {stat_name(told['stat'])} ({told['stat']}), but no stat acts")
        else:
            parts.append(f"denies that it acts on {stat_name(value['stat'])} ({value['stat']})")
    if told["labels"] != value["labels"]:
        parts.append(_diff(told["labels"], value["labels"]) if value["labels"] or told["labels"] else "")
        if not value["labels"]:
            parts[-1] = f"claims {', '.join(told['labels'])}, but it tastes like plain water"
    return "; ".join(p for p in parts if p)


# --- one claim -----------------------------------------------------------------------------------


def _claim(item: dict, entry: dict, sheet: dict, facts: dict, table: dict) -> dict:
    kind, focus, told = entry["type"], sheet["focus"], entry["told"]
    fact = facts.get(entry["fact"], {})
    out = {"n": item["n"], "type": kind, "true": entry["true"], "vague": entry["vague"]}
    if kind == "alias":
        out["says"] = f'"{fact["alias"]}" is a folk name for {told}'
        if not entry["true"]:
            out["truth"] = f'"{fact["alias"]}" is a folk name for {fact["value"]}'
            shared = [g for g, m in table["groups"].items() if {told, fact["value"]} <= set(m)]
            out["issue"] = (f"it means {fact['value']}, not {told}" +
                            (f" (both grow at {shared[0]}, so locals mix them up)" if shared else ""))
    elif kind == "group":
        out["says"] = f"{focus} grows wild at {told['group']}"
        if not entry["true"]:
            out["truth"] = f"{focus} grows wild at {fact['group']}"
            homes = [g for g, m in table["groups"].items() if focus in m]
            out["issue"] = f"{focus} does not grow at {told['group']}; it grows at {', '.join(homes)}"
    elif kind == "soil":
        out["says"] = f"{focus} in {fact['soil']} earth: {told}"
        if not entry["true"]:
            out["truth"] = f"{focus} in {fact['soil']} earth: {fact['value']}"
            out["issue"] = f"it is {fact['value']} there, not {told}"
    elif kind in ("pair", "triple"):
        names = [focus] + [ref_words(r) for r in entry["refs"]]
        out["says"] = f"a brew of {', '.join(names)}: {_effects(_brew_effects(told))}"
        out["names"] = _names(entry["refs"])
        out["hidden"] = {"plants": fact["plants"], "label pairs": _pairs(fact["plants"]),
                         "labels cancel": bool(secondary_labels(fact["plants"])) and not noticed(secondary_labels(fact["plants"]))}
        if not entry["true"]:
            value = fact["value"]
            out["truth"] = f"a brew of {', '.join(names)}: {_effects(_brew_effects(value))}"
            out["issue"] = _brew_issue(told, value)
    elif kind == "mix":
        out.update(_mix_claim(entry, fact, sheet))
    elif kind == "trial":
        out.update(_trial_claim(entry, focus))
    return out


def _reveal_words(reveal: dict) -> tuple[list[str], list[str]]:
    alone = [reveal["second"]] if reveal.get("second") else []
    mixed = ([reveal["primary"]] if reveal.get("primary") else []) + list(reveal.get("secondary") or [])
    return alone, mixed


def _mix_claim(entry: dict, fact: dict, sheet: dict) -> dict:
    second = fact["second"]
    words = f"all three plants of {second['group']}" if "group" in second else \
        " and ".join(ref_words(r) for r in second["refs"])
    first = " and ".join(fact["named"])

    def say(reveal):
        alone, mixed = _reveal_words(reveal)
        return (f"a brew of {first} poured into a brew of {words}: " +
                (f"the second brew alone: {_effects(alone)}; " if alone else "") + f"the mix: {_effects(mixed)}")

    out = {"says": say(entry["told"]), "names": _names(second.get("refs", [])),
           "hidden": {"plants": fact["plants"], "second brew": second["plants"], "label pairs": _pairs(fact["plants"]),
                      "everything the mix does": fact["value"]}}
    if not entry["true"]:
        out["truth"] = say(fact["reveal"])
        told_alone, told_mixed = _reveal_words(entry["told"])
        true_alone, true_mixed = _reveal_words(fact["reveal"])
        issues = []
        if told_alone != true_alone:
            issues.append("the second brew alone " + _diff(told_alone, true_alone))
        if told_mixed != true_mixed:
            issues.append("the mix " + _diff(told_mixed, true_mixed))
        out["issue"] = "; ".join(issues)
    return out


def _trial_claim(entry: dict, stat: str) -> dict:
    def say(told):
        poured = "".join(f", with a brew of {' and '.join(b)} poured in" for b in entry["added"])
        change = round(100 * (told["after"] - told["before"]) / told["before"])
        effects = ([told["stat"]] if told["stat"] else []) + list(told["noticed"])
        return (f"a brew of {', '.join(entry['base'])}{poured}: work {told['before']} -> {told['after']} "
                f"({change:+d}%); {_effects(effects) if effects else 'the work did not change; it tastes like plain water'}")

    labels = entry["labels"]
    out = {"says": say(entry["told"]), "role": entry["role"],
           "hidden": {"base counts": entry["base"], "poured counts": entry["added"],
                      "label pairs": _pairs([*entry["base"], *(p for b in entry["added"] for p in b)]),
                      "base": f"{signed(entry['base'], stat):+d}% {stat}",
                      "net modifier": f"{net_modifier(labels):+d}%", "result": f"{entry['result']:+d}% {stat}"}}
    if not entry["true"]:
        out["truth"] = say(entry["value"])
        told, value = entry["told"], entry["value"]
        issues = []
        if (told["before"], told["after"]) != (value["before"], value["after"]):
            issues.append(f"the work is {told['before']} -> {told['after']}, but the true change is "
                          f"{value['before']} -> {value['after']}")
        if told["noticed"] != value["noticed"]:
            issues.append("noticed: " + (_diff(told["noticed"], value["noticed"]) if value["noticed"]
                                         else f"claims {', '.join(told['noticed'])}, but it tastes like plain water"))
        out["issue"] = "; ".join(issues)
    return out


def _more_claim(item: dict, extra: dict) -> dict:
    out = {"n": item["n"], "type": "identity", "true": extra["true"], "vague": False,
           "says": f"in the mix above, the plant of {extra['group']} was {extra['told']}"}
    if not extra["true"]:
        out["truth"] = f"in the mix above, the plant of {extra['group']} was {extra['value']}"
        out["issue"] = f"it was {extra['value']}, not {extra['told']}"
    return out


# --- one source ----------------------------------------------------------------------------------


def metadata(sheet: dict, facts: dict | None = None, table: dict | None = None) -> dict:
    facts = facts or {f["id"]: f for f in load_catalogue()}
    table = table or load_plants()
    entries = {e["fact"]: e for e in sheet["facts"]}
    claims = []
    for item in items(sheet):
        entry = entries[item["fact"]]
        claims.append(_more_claim(item, entry) if entry["type"] == "more" else _claim(item, entry, sheet, facts, table))
        if entry["type"] == "mix" and (extra := entries.get(f"more:{entry['fact']}")) and extra["what"] != "plant":
            part = "the mix also" if extra["what"] == "effect" else "the second brew alone also"
            claims[-1]["also"] = {"says": f"{part}: {_effects([extra['told']])}", "true": extra["true"]}
            if not extra["true"]:
                claims[-1]["also"].update(truth=f"{part}: {_effects([extra['value']])}",
                                          issue=f"says {extra['told']} instead of {extra['value']}")
    return {
        "id": sheet["id"], "kind": sheet["kind"], "shown as": KIND_NAMES[sheet["kind"]], "focus": sheet["focus"],
        "words": sheet["words"], "padding": sheet["padding"],
        "teaches": [c["says"] for c in claims if c["true"]] +
                   [c["also"]["says"] for c in claims if c.get("also", {}).get("true")],
        "false claims": [{"n": c["n"], "says": c["says"], "truth": c["truth"], "issue": c["issue"]}
                         for c in claims if not c["true"]] +
                        [{"n": c["n"], **{k: c["also"][k] for k in ("says", "truth", "issue")}}
                         for c in claims if c.get("also") and not c["also"]["true"]],
        "claims": claims,
    }


def write_metadata(sheet: dict, facts: dict | None = None, table: dict | None = None):
    folder = folder_of(sheet["id"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "metadata.json"
    path.write_text(json.dumps(metadata(sheet, facts, table), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str]) -> None:
    sheets = json.loads(SHEETS_FILE.read_text(encoding="utf-8"))
    if argv:
        sheets = [s for s in sheets if s["id"] in set(argv)]
    facts, table = {f["id"]: f for f in load_catalogue()}, load_plants()
    for sheet in sheets:
        write_metadata(sheet, facts, table)
    print(f"metadata.json written for {len(sheets)} sources")


if __name__ == "__main__":
    main(sys.argv[1:])
