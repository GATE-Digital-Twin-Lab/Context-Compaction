"""The hidden content tables obey the rules in the spec (Plant names and groups; Sources)."""

import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from corpus.catalogue import CATALOGUE_FILE, STYLES, about, catalogue, dump, revealable
from corpus.myths import FALLIBLE, MYTHS_FILE, myth_pool
from corpus.myths import dump as myth_dump
from environment.brewer import PLANTS, STAT_SETS

TABLE = json.loads((Path(__file__).parent.parent / "content" / "plants.json").read_text(encoding="utf-8"))


def test_three_unique_aliases_per_plant():
    aliases = TABLE["aliases"]
    assert set(aliases) == set(PLANTS) and all(len(names) == 3 for names in aliases.values())
    every = [name.lower() for names in aliases.values() for name in names]
    assert len(set(every)) == 24 and not set(every) & set(PLANTS)


def test_eight_groups_of_three_with_every_plant_in_three():
    groups = [frozenset(members) for members in TABLE["groups"].values()]
    assert len(groups) == 8 and all(len(g) == 3 for g in groups)
    assert Counter(p for g in groups for p in g) == dict.fromkeys(PLANTS, 3)


def test_two_plants_share_at_most_one_group_and_no_group_is_a_stat_set():
    groups = [frozenset(members) for members in TABLE["groups"].values()]
    assert all(len(a & b) <= 1 for a, b in combinations(groups, 2))
    assert not set(groups) & {frozenset(s) for s in STAT_SETS.values()}
    assert TABLE["groups"]["the mill pond"] == ["mint", "elderberry", "nettle"]


# --- the fact catalogue ------------------------------------------------------------------------

def test_catalogue_file_is_up_to_date():
    assert CATALOGUE_FILE.read_text(encoding="utf-8") == dump(catalogue()), "run: python -m corpus.catalogue"


def test_catalogue_rows():
    facts = catalogue()
    kinds = Counter(f["type"] if f["type"] != "brew" else f"brew{len(f['plants'])}" for f in facts)
    assert kinds == {"alias": 24, "group": 24, "soil": 24, "brew2": 28, "brew3": 56, "mix": 48}
    assert len({f["id"] for f in facts}) == len(facts)
    triples = Counter((f["value"]["stat"], len(f["value"]["labels"])) for f in facts if f["type"] == "brew" and len(f["plants"]) == 3)
    assert {k: v for k, v in triples.items() if k[0]} == {("I", 0): 1, ("S", 0): 1, ("V", 0): 1, ("D", 0): 1}
    assert next(f for f in facts if f["id"] == "brew:nettle+chamomile")["value"] == {"stat": None, "labels": ["warming"]}
    assert next(f for f in facts if f["id"] == "soil:dill:brown")["value"] == "sometimes fails"
    assert all(len(about(p, facts)) == 3 + 3 + 3 + 7 + 21 + 6 for p in PLANTS)


def test_mixes_are_balanced_per_plant():
    facts = [f for f in catalogue() if f["type"] == "mix"]
    for plant in PLANTS:
        mine = [f for f in facts if f["focus"] == plant]
        assert len(mine) == 6 and all(plant in f["named"] and len(f["named"]) == 2 for f in mine)
        assert Counter(f["kind"] for f in mine) == {"2+2": 3, "3+2": 3}
        assert sorted(f["second"]["style"] for f in mine if f["kind"] == "2+2") == sorted(STYLES)
        assert all(f["second"]["plants"] == TABLE["groups"][f["second"]["group"]] for f in mine if f["kind"] == "3+2")
        assert sum("W" in revealable(f["plants"])[0] for f in mine) == 1
        assert [f["reveal"]["primary"] for f in mine if "W" in revealable(f["plants"])[0]] == ["W"]


def test_mix_reveals_follow_the_rules():
    for f in (f for f in catalogue() if f["type"] == "mix"):
        assert f["plants"] == sorted(set(f["named"]) | set(f["second"]["plants"]), key=PLANTS.index)
        primaries, secondaries = revealable(f["plants"])
        reveal = f["reveal"]
        assert reveal["primary"] or reveal["secondary"]
        assert reveal["primary"] in primaries + [None] and reveal["secondary"] in secondaries + [None]
        if f["kind"] == "2+2":
            assert not (reveal["primary"] and reveal["secondary"])
            assert reveal["second"] is None or any("group" in ref for ref in f["second"]["refs"])
        else:
            assert bool(reveal["primary"]) == bool(primaries) and bool(reveal["secondary"]) == bool(secondaries)


def test_what_a_drinker_notices():
    assert revealable({"mint", "sage", "elderberry", "dill", "rosemary"}) == (["I"], [])     # labels cancel
    assert revealable({"elderberry", "nettle", "sage", "rosemary"}) == ([], ["toxic"])        # undrinkable
    assert revealable({"mint", "sage", "chamomile"}) == ([], ["fragrant", "sweet"])
    assert revealable({"mint", "nettle", "sage", "basil", "rosemary"})[0] == ["V", "D"]       # two stats


# --- the myth pool -----------------------------------------------------------------------------


def test_myth_file_is_up_to_date():
    assert MYTHS_FILE.read_text(encoding="utf-8") == myth_dump(myth_pool(catalogue(), TABLE)), "run: python -m corpus.myths"


def test_every_fact_has_a_different_wrong_myth_per_kind():
    facts = {f["id"]: f for f in catalogue()}
    pool = myth_pool(list(facts.values()), TABLE)
    assert set(pool) == set(facts)
    for fid, myths in pool.items():
        fact = facts[fid]
        assert tuple(myths) == FALLIBLE
        values = list(myths.values())
        assert all(v not in values[:i] for i, v in enumerate(values))                    # kinds disagree
        truth = fact["reveal"] if fact["type"] == "mix" else fact["value"]
        assert truth not in values                                                        # never the truth
        if fact["type"] == "alias":                                                       # a local confusion
            assert all(any({fact["value"], v} <= set(m) for m in TABLE["groups"].values()) for v in values)
        if fact["type"] == "group":                                                       # moved, never denied
            assert all(fact["plants"][0] not in TABLE["groups"][v["group"]] for v in values)
        if fact["type"] == "brew" and len(fact["plants"]) == 2:
            assert all(v["stat"] is None and len(v["labels"]) <= 1 for v in values)
        if fact["type"] == "mix":                                                         # one revealed effect changed
            assert all(sum(v[k] != truth[k] for k in truth) == 1 for v in values)
            assert all(v[k] for v in values for k in truth if truth[k])
