"""Layer 4 without a model: briefs, the comparison of a blind reading, stray names, cue novelty, parsing."""

import json

import pytest

from corpus.briefs import allowed_names, check_cues, compare, items, parse_ref, stray_names, too_close
from corpus.sheets import SHEETS_FILE
from corpus.texts import path_of
from corpus.write import parse_reader, parse_writer, reader_system, writer_system, writer_user

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


def test_cue_spans_must_be_present_complete_and_new():
    sheet_items = items(BY_ID["pamphlet:mint:13"])          # F1 nothing (sweet and bitter cancel), F2 mix (shimmering; I), F3 V
    body = ("Mint with Old Gilly's herb and dill tastes of nothing, like well water.\n"
            "The second pot shines in the cup like a new penny.\nThe mix makes a man count sheep faster.\n"
            "Mint, nettle and Ysolde's sprig had my uncle ploughing till dark.")
    cues = [{"fact": "F2", "effect": "shimmering", "span": "shines in the cup like a new penny"},
            {"fact": "F2", "effect": "I", "span": "count sheep faster"},
            {"fact": "F3", "effect": "V", "span": "had my uncle ploughing till dark"}]
    assert check_cues(body, sheet_items, cues, {}) == []
    assert len(check_cues(body, sheet_items, cues[1:], {})) == 1                       # shimmering has no span
    assert len(check_cues(body, sheet_items, cues, {"shimmering": ["it shines in the cup like a penny"]})) == 1
    missing = cues[:-1] + [{"fact": "F3", "effect": "V", "span": "not in the text"}]
    assert len(check_cues(body, sheet_items, missing, {})) == 1


def test_novelty():
    assert too_close("the smell clung to her shawl", ["the smell clung to his shirt for days"])
    assert not too_close("the neighbours asked what was on the fire", ["the smell clung to his shirt"])
    # a long sentence sharing a few common words with a short earlier phrase is not a repeat ...
    assert not too_close("her hands, white-knuckled around the cup, went slack halfway through, and set it down",
                         ["the chill went out of his fingers before he had set the cup down"])
    # ... but one that reuses most of its words is
    assert too_close("The steam alone made her stop in the doorway and close her eyes",
                     ["the steam alone made whoever passed stop and close their eyes"])
    assert not too_close("the cat came", ["the cat left"])                       # one shared stem is never enough


def test_parsing_the_writer_and_the_reader():
    raw = ('<think>x</think>\nTITLE: A Tale\nAUTHOR: Ned, a carter\n<text>\nHe came. He went.\n</text>\n'
           '<cues>\n```json\n[{"fact": "F1", "effect": "sweet", "span": "He came"}]\n```\n</cues>')
    assert parse_writer(raw) == ("A Tale", "Ned, a carter", "He came. He went.",
                                 [{"fact": "F1", "effect": "sweet", "span": "He came"}])
    with pytest.raises(ValueError):
        parse_writer("TITLE: A Tale\n<text>x</text>")
    assert parse_reader('<facts>[{"type": "alias", "name": "Ferrow", "plant": "dill"}]</facts>')[0]["plant"] == "dill"


def test_prompts_build_for_every_kind():
    for kind in ("book", "transcript", "herbal", "pamphlet", "folk"):
        sheet = BY_ID[f"{kind}:sage:01"]
        system, user = writer_system(sheet), writer_user(sheet, {"sweet": ["an old image"]}, ["a problem"])
        assert f"about {sheet['words']} words" in system and "<cues>" in system
        assert "<example>" in user and "F1." in user and "- a problem" in user
    assert "<facts>" in reader_system() and "Ferrow" not in reader_system()        # the reader gets no answers
