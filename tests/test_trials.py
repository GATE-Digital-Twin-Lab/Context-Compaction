"""The trial ledgers (corpus/trials.py) and the sources' metadata (corpus/metadata.py)."""

import json
from collections import Counter

from corpus.briefs import compare, items
from corpus.catalogue import noticed
from corpus.metadata import metadata
from corpus.sheets import SHEETS_FILE
from corpus.trials import BASE_LEVELS, ROLES, ledgers, signed
from environment.brewer import STAT_SETS, apply_modifier, effect_of, net_modifier

LEDGERS = ledgers()
SHEETS = json.loads(SHEETS_FILE.read_text(encoding="utf-8"))


def _summed(trial):
    total = Counter(trial["base"])
    for brew in trial["added"]:
        total.update(brew)
    return dict(total)


def test_one_ledger_per_stat_in_the_sheets():
    assert [ledger["focus"] for ledger in LEDGERS] == list(STAT_SETS)
    assert [s for s in SHEETS if s["kind"] == "trials"] == LEDGERS
    for ledger in LEDGERS:
        roles = [e["role"] for e in ledger["facts"]]
        assert len(roles) == len(set(roles)) and set(roles) <= set(ROLES) and "alone" in roles
        poured = [tuple(sorted(tuple(sorted(b)) for b in e["added"])) for e in ledger["facts"]]
        assert len(poured) == len(set(poured))                       # a reader can tell the entries apart


def test_every_trial_is_what_the_brewer_gives():
    for ledger in LEDGERS:
        stat = ledger["focus"]
        for e in ledger["facts"]:
            assert sorted(e["base"]) == sorted(STAT_SETS[stat]) and abs(signed(e["base"], stat)) in BASE_LEVELS
            effect = effect_of(_summed(e))
            assert signed(_summed(e), stat) == e["result"] and list(effect.secondary) == e["labels"]
            assert effect.drinkable and set(effect.positive) | set(effect.negative) <= {stat}
            v = e["value"]
            assert v["after"] * 100 == v["before"] * (100 + e["result"])           # the work shows the result
            assert v["noticed"] == noticed(e["labels"]) and v["stat"] == (stat if e["result"] else None)
            if e["role"] in ("boost", "weaken", "negative", "cancel"):              # label-driven, exact
                base = signed(e["base"], stat)
                assert e["result"] == (1 if base > 0 else -1) * apply_modifier(abs(base), net_modifier(e["labels"]))
                assert abs(base) * (100 + net_modifier(e["labels"])) % 100 == 0
            if e["role"] == "cancel":
                assert e["labels"] and v["noticed"] == []


def test_a_wrong_trial_changes_one_thing_and_stays_noticeable():
    for ledger in LEDGERS:
        for e in ledger["facts"]:
            assert (e["told"] == e["value"]) == e["true"]
            assert noticed(e["told"]["noticed"]) == e["told"]["noticed"]
            if not e["true"]:
                numbers = (e["told"]["before"], e["told"]["after"]) != (e["value"]["before"], e["value"]["after"])
                assert numbers != (e["told"]["noticed"] != e["value"]["noticed"])   # exactly one of the two


def test_a_perfect_reading_of_a_ledger_passes_and_a_wrong_count_fails():
    sheet_items = items(LEDGERS[1])
    reading = [{"type": "trial", "plants": [k[1] for k in i["key"][1]], "added": [[k[1] for k in b] for b in i["key"][2]],
                **i["value"]} for i in sheet_items]
    assert compare(sheet_items, reading) == []
    reading[0] = {**reading[0], "after": reading[0]["after"] + 1}
    assert len(compare(sheet_items, reading)) == 1


def test_metadata_lists_every_claim_and_explains_every_false_one():
    for sheet in SHEETS:
        meta = metadata(sheet)
        assert [c["n"] for c in meta["claims"]] == [i["n"] for i in items(sheet)]
        false = [c for c in meta["claims"] if not c["true"]]
        assert len(meta["teaches"]) >= len(meta["claims"]) - len(false)
        assert all(c["issue"] and c["truth"] != c["says"] for c in false), sheet["id"]
        assert {f["n"] for f in meta["false claims"]} >= {c["n"] for c in false}
    s_ledger = metadata(LEDGERS[1])
    assert all("hidden" in c and "net modifier" in c["hidden"] for c in s_ledger["claims"])
