"""The hidden content tables obey the rules in the spec (Plant names and groups; Sources)."""

import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from corpus.catalogue import CATALOGUE_FILE, STYLES, about, catalogue, dump, noticed, revealable
from corpus.myths import FALLIBLE, MYTHS_FILE, myth_pool
from corpus.myths import dump as myth_dump
from corpus.sheets import BOOK, KINDS, SHEETS_FILE, SPEC, build, truth
from corpus.sheets import dump as sheet_dump
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
    assert next(f for f in facts if f["id"] == "brew:nettle+chamomile")["value"] == {"stat": None, "labels": ["shimmering"]}
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
        assert reveal["primary"] in primaries + [None] and reveal["secondary"] in (secondaries, None)   # all labels
        if f["kind"] == "2+2":
            assert not (reveal["primary"] and reveal["secondary"])
            assert reveal["second"] is None or any("group" in ref for ref in f["second"]["refs"])
        else:
            assert bool(reveal["primary"]) == bool(primaries) and bool(reveal["secondary"]) == bool(secondaries)


def test_what_a_drinker_notices():
    assert noticed(["sweet", "fragrant"]) == ["fragrant", "sweet"]                          # all, when they agree
    assert noticed(["sweet", "bitter"]) == [] and noticed(["toxic", "shimmering"]) == []        # cancel: like water
    assert noticed(["fragrant", "fragrant"]) == ["fragrant"]                                 # two pairs, one taste
    assert revealable({"mint", "sage", "elderberry", "dill", "rosemary"}) == (["I"], [])     # labels cancel
    assert revealable({"elderberry", "nettle", "sage", "rosemary"}) == ([], ["murky", "toxic"])   # undrinkable
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
        if fact["type"] == "brew":                                                        # no opposing labels
            assert all(noticed(v["labels"]) == v["labels"] for v in values)
        if fact["type"] == "mix":                                                         # one revealed effect changed
            assert all(sum(v[k] != truth[k] for k in truth) == 1 for v in values)
            assert all(v[k] for v in values for k in truth if truth[k])


# --- the source sheets -------------------------------------------------------------------------

ALL_SHEETS, SHEET_STATS = build()
SHEETS = [s for s in ALL_SHEETS if s["kind"] != "trials"]          # the plant sources; ledgers: tests/test_trials.py
FACTS = {f["id"]: f for f in catalogue()}
MYTHS = json.loads(MYTHS_FILE.read_text(encoding="utf-8"))


def _of(kind, plant=None):
    return [s for s in SHEETS if s["kind"] == kind and plant in (None, s["focus"])]


def test_sheet_file_is_up_to_date():
    assert SHEETS_FILE.read_text(encoding="utf-8") == sheet_dump(ALL_SHEETS), "run: python -m corpus.sheets"


def test_sheets_per_plant_and_kind():
    for plant in PLANTS:
        assert {k: len(_of(k, plant)) for k in KINDS} == {k: SPEC[k]["count"] for k in KINDS}
    assert all(SPEC[s["kind"]]["words"][0] <= s["words"] <= SPEC[s["kind"]]["words"][1] for s in SHEETS)


def test_facts_come_from_the_focus_plant_and_are_not_repeated():
    for s in SHEETS:
        rows = {f["id"] for f in about(s["focus"], list(FACTS.values()))}
        ids = [e["fact"] for e in s["facts"]]
        assert len(ids) == len(set(ids))
        assert all(e["fact"] in rows or e["type"] == "more" and e["of"] in rows for e in s["facts"])


def test_what_each_kind_states():
    for plant in PLANTS:
        book = _of("book", plant)[0]
        assert Counter(e["type"] for e in book["facts"]) == BOOK and all(e["true"] for e in book["facts"])
        transcripts = _of("transcript", plant)
        extras = [e for s in transcripts for e in s["facts"] if e.get("extra") or e["type"] == "more"]
        assert len(extras) == 1 and extras[0]["type"] in ("alias", "group", "more")
        assert all(sum(e["type"] in ("pair", "triple", "mix") and e not in extras for e in s["facts"]) == 5
                   for s in transcripts)
        brews_mixes = {f["id"] for f in about(plant, list(FACTS.values())) if f["type"] in ("brew", "mix")}
        assert {e["fact"] for s in transcripts for e in s["facts"]} >= brews_mixes      # 40 slots cover all 34
        herbal = _of("herbal", plant)
        assert all(sum(e["type"] in ("alias", "group", "soil") for e in s["facts"]) == 4 for s in herbal)
        assert sum(e["type"] in ("pair", "triple") for s in herbal for e in s["facts"]) == 1
        assert not any(e["type"] == "mix" for s in herbal for e in s["facts"])
        assert all(1 <= len(s["facts"]) <= 3 for k in ("pamphlet", "folk") for s in _of(k, plant))


def test_told_is_the_truth_or_the_kinds_myth():
    for s in SHEETS:
        for e in s["facts"]:
            if e["type"] == "more":
                assert (e["told"] == e["value"]) == e["true"]
            else:
                expected = truth(FACTS[e["fact"]]) if e["true"] else MYTHS[e["fact"]][s["kind"]]
                assert e["told"] == expected


def test_truth_rates_are_near_each_kinds_rate():
    for kind in KINDS:
        stated = [e for s in _of(kind) for e in s["facts"]]
        assert abs(sum(e["true"] for e in stated) / len(stated) - SPEC[kind]["rate"]) < 0.06


def test_references_stay_true():
    for s in SHEETS:
        for e in s["facts"]:
            for ref in e.get("refs", []):
                assert "alias" not in ref or TABLE["aliases"][ref["plant"]].count(ref["alias"]) == 1
                assert "group" not in ref or ref["plant"] in TABLE["groups"][ref["group"]]
            if e["type"] in ("pair", "triple"):
                assert sorted(r["plant"] for r in e["refs"]) == sorted(p for p in FACTS[e["fact"]]["plants"] if p != s["focus"])
                if s["kind"] in ("book", "transcript"):
                    assert all(set(r) == {"plant"} for r in e["refs"])                  # official names
        used = {r["alias"] for e in s["facts"] for r in e.get("refs", []) if "alias" in r}
        assert not any(e["type"] == "alias" and not e["true"] and FACTS[e["fact"]]["alias"] in used for e in s["facts"])


def test_pool_guarantee():
    """Every soil hint and brew has a true source naming its plants (name or alias); every mix a true source."""
    for fid, fact in FACTS.items():
        if fact["type"] in ("soil", "brew", "mix"):
            assert any(e["fact"] == fid and e["true"] and all("group" not in r for r in e.get("refs", []) if fact["type"] == "brew")
                       for s in SHEETS for e in s["facts"]), fid


# --- the glossary --------------------------------------------------------------------------------

from corpus.glossary import entries, load_glossary, verbatim  # noqa: E402
from environment.brewer import MODIFIERS  # noqa: E402


def test_glossary_covers_every_stat_and_label():
    glossary = load_glossary()
    assert set(glossary["stats"]) == set(STAT_SETS) and set(glossary["labels"]) == set(MODIFIERS)
    for e in glossary["stats"].values():
        assert len(e["more"]) + len(e["less"]) >= 6 and len(e["trades"]) >= 3
    assert all(len(e["cues"]) >= 2 for e in glossary["labels"].values())


def test_every_glossary_phrase_points_to_one_stat_or_label():
    owner = {}
    for key, phrases in entries().items():
        for phrase in phrases:
            assert owner.setdefault(phrase.lower(), key) == key, phrase                  # listed once
    for key, phrases in entries().items():                   # and no phrase contains another key's phrase
        assert all(owner[found] == key for phrase in phrases for found in verbatim(phrase)), key


def test_verbatim_finds_copied_phrases_only():
    assert verbatim("He had a Powerful   grip and was STRONG.") == ["a powerful grip", "strong"]
    assert verbatim("He could heave a millstone onto the cart unaided.") == []
    assert verbatim("the stonecutters") == [] and verbatim("unwise") == []          # whole words only


# --- the cue bank and the texts ----------------------------------------------------------------

from corpus.texts import TEXTS_DIR, load_cues, one_sentence_per_line, path_of, problems  # noqa: E402


def test_cue_bank_has_distinct_cues_far_from_the_glossary():
    cues = load_cues()
    assert set(cues) == set(MODIFIERS) and all(len(c) >= 10 for c in cues.values())
    every = [c.lower() for cs in cues.values() for c in cs]
    assert len(every) == len(set(every))
    assert not {c: verbatim(c) for c in every if verbatim(c)}                 # no glossary wording or image


def test_one_sentence_per_line():
    assert one_sentence_per_line("He came. He went.\n| a. b |\nIV. Of mixtures. Two brews.") == \
        "He came.\nHe went.\n| a. b |\nIV. Of mixtures.\nTwo brews.\n"


def test_written_texts_pass_the_mechanical_checks():
    """Every accepted text sits in its source's folder, named after it, and passes the checks."""
    for path in TEXTS_DIR.glob("*/*.txt"):
        if path.name == "failed.txt":
            continue
        sheet_id = path.parent.name.replace("-", ":")
        sheet = next(s for s in ALL_SHEETS if s["id"] == sheet_id)
        assert path_of(sheet_id) == path and problems(path, sheet) == [], path.name
    assert not list(TEXTS_DIR.glob("*.txt")), "texts belong in their source's folder"
