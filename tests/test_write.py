"""Layer 4 without a model: briefs, the comparison of a blind reading, stray names, cue novelty, parsing."""

import json

import pytest

from corpus.briefs import allowed_names, compare, items, parse_ref, stray_names
from corpus.sheets import SHEETS_FILE
from corpus.texts import path_of
from corpus.write import parse_reader, reader_system

SHEETS = json.loads(SHEETS_FILE.read_text(encoding="utf-8"))
BY_ID = {s["id"]: s for s in SHEETS}
HAND_WRITTEN = ["book:mint:01", "transcript:mint:04", "herbal:mint:05", "pamphlet:mint:13", "folk:mint:03",
                "trials:S"]


def _ref_text(key):
    kind, name = key
    return {"plant": name, "alias": name, "group": f"a plant of {name}", "whole": f"all plants of {name}"}[kind]


def perfect_reading(sheet_items):
    """What a reader that gets everything right would answer."""
    out = []
    for item in sheet_items:
        key, value = item["key"], item["value"]
        if key[0] == "alias":
            out.append({"type": "alias", "name": key[1], "plant": value})
        elif key[0] == "group":
            out.append({"type": "place", "plant": key[1], "place": key[2]})
        elif key[0] == "soil":
            out.append({"type": "soil", "plant": key[1], "earth": key[2], "growth": value})
        elif key[0] == "brew":
            out.append({"type": "brew", "plants": [_ref_text(k) for k in key[1]], "effects": value})
        elif key[0] == "mix":
            out.append({"type": "mix", "first": [_ref_text(k) for k in key[1]],
                        "second": [_ref_text(k) for k in key[2]], **value})
        elif key[0] == "identity":
            out.append({"type": "identity", "ref": _ref_text(key[1]), "plant": value})
        elif key[0] == "trial":
            out.append({"type": "trial", "plants": [_ref_text(k) for k in key[1]],
                        "added": [[_ref_text(k) for k in brew] for brew in key[2]], **value})
    return out


def test_every_sheet_has_a_brief_with_distinct_claims():
    for sheet in SHEETS:
        sheet_items = items(sheet)
        assert sheet_items and all(i["brief"] for i in sheet_items)
        keys = [i["key"] for i in sheet_items]
        assert len(keys) == len(set(keys)), sheet["id"]


def test_a_perfect_reading_passes_for_every_sheet():
    for sheet in SHEETS:
        sheet_items = items(sheet)
        assert compare(sheet_items, perfect_reading(sheet_items)) == [], sheet["id"]


def test_a_wrong_missing_or_extra_claim_fails():
    sheet_items = items(BY_ID["pamphlet:mint:13"])
    reading = perfect_reading(sheet_items)
    wrong = json.loads(json.dumps(reading))
    wrong[2]["effects"] = ["S"]                                        # V read as S
    assert len(compare(sheet_items, wrong)) == 1
    assert len(compare(sheet_items, reading[1:])) == 1                 # one claim missed
    extra = reading + [{"type": "place", "plant": "mint", "place": "Ludding"}]
    assert len(compare(sheet_items, extra)) == 1


def test_references_as_a_reader_writes_them():
    assert parse_ref("Mint") == ("plant", "mint")
    assert parse_ref("Old Gilly\u2019s herb") == ("alias", "old gilly's herb")
    assert parse_ref("a plant of the mill pond") == ("group", "mill pond")
    assert parse_ref("all three plants of Coldharbour") == ("whole", "coldharbour")
    assert parse_ref("some weed")[0] == "unknown"


def test_hand_written_texts_use_only_their_sheets_names():
    for sid in HAND_WRITTEN:
        assert stray_names(path_of(sid).read_text(encoding="utf-8"), BY_ID[sid]) == [], sid
    assert stray_names("They met at Ludding and drank rosemary.", BY_ID["folk:mint:03"]) == ["rosemary", "Ludding"]
    assert "mill pond" in allowed_names(BY_ID["transcript:mint:04"])["places"]


def test_parsing_the_reader():
    assert parse_reader('<facts>[{"type": "alias", "name": "Ferrow", "plant": "dill"}]</facts>')[0]["plant"] == "dill"
    assert "<facts>" in reader_system() and "Ferrow" not in reader_system()        # the reader gets no answers
