"""Layer 4, piece by piece (corpus/compose.py, corpus/write.py), with fake model clients."""

import json
import re
from types import SimpleNamespace

import pytest

import corpus.texts as texts
import corpus.write as write
from corpus import compose
from corpus.briefs import items
from corpus.compose import Piece
from corpus.sheets import SHEETS_FILE
from test_write import perfect_reading

SHEETS = {s["id"]: s for s in json.loads(SHEETS_FILE.read_text(encoding="utf-8"))}


def test_labels_of_a_claim_and_the_piece_prompt():
    book = items(SHEETS["book:mint:01"])
    trial = items(SHEETS["trials:S"])[1]                                   # +S 60, three labels
    assert compose.labels_of(trial) == ["fragrant", "shimmering", "sweet"]  # the stat shows in the counts
    alias = next(i for i in book if i["type"] == "alias")
    assert compose.labels_of(alias) == []
    prompt = compose.piece_prompt(Piece(trial), {"sweet": ["a", "b", "c", "d"]})
    assert "obvious image" in prompt and "- sweet: a; b; c" in prompt and "<piece>" in prompt
    assert "obvious image" not in compose.piece_prompt(Piece(alias), {})


def test_a_brew_piece_must_name_its_plants():
    sheet = SHEETS["pamphlet:dill:01"]
    brew = items(sheet)[0]                                   # dill, "a plant of Wendle Cross", "Remy's herb"
    assert compose.brew_names(brew) == ["remy's herb", "wendle cross", "dill"]
    assert compose.check_brew_names("Dill, a plant of Wendle Cross and Remy\u2019s herb together.", brew) == []
    problem = compose.check_brew_names("Dill and Remy's herb together.", brew)
    assert problem and "never names wendle cross" in problem[0]
    group = next(i for i in items(sheet) if i["type"] == "group")
    assert compose.brew_names(group) == [] and compose.check_brew_names("Nothing here.", group) == []
    assert "Name every plant" in compose.piece_prompt(Piece(brew), {})
    assert "Name every plant" not in compose.piece_prompt(Piece(group), {})


def test_parse_piece():
    assert compose.parse_piece("thinking aside <piece>Mint and dill.</piece>") == "Mint and dill."
    with pytest.raises(ValueError, match="piece"):
        compose.parse_piece("Mint and dill.")


def test_layout_by_kind():
    book = compose.layout(SHEETS["book:mint:01"])
    assert book[0] == ("pad", 0) and ("heading", "I. Of its names and where it grows") in book
    ledger = compose.layout(SHEETS["trials:S"])
    assert [v for k, v in ledger if k == "heading"] == ["Monday.", "Tuesday.", "Wednesday.", "Thursday.", "Friday.", "Saturday."]
    pamphlet = compose.layout(SHEETS["pamphlet:mint:13"])
    assert [k for k, _ in pamphlet] == ["pad", "bullet", "bullet", "bullet", "pad"]
    tale = compose.layout(SHEETS["herbal:mint:05"])
    assert [k for k, _ in tale][:3] == ["pad", "piece", "pad"]
    assert sum(compose.pad_plan(SHEETS["herbal:mint:05"])) <= SHEETS["herbal:mint:05"]["words"]


class FakeModel:
    """Writes every piece with fresh nonsense images and reads by the piece markers it wrote, perfectly,
    except that the first reading of piece F2 alone misses it."""

    def __init__(self, sheet_items):
        self.items = {i["n"]: i for i in sheet_items}
        self.count = 0
        self.misread = {"F2"}

    def complete(self, messages, seed):
        self.count += 1
        user = messages[-1]["content"]
        if messages[0]["content"].startswith("You read one source text"):
            found = [n for n in re.findall(r"\bpiece (F\d+)\b", user) if n in self.items]
            if len(found) == 1 and found[0] in self.misread:
                self.misread.discard(found[0])
                found = []
            return self._answer("<facts>" + json.dumps(perfect_reading([self.items[n] for n in found])) + "</facts>")
        if user.startswith("Invent the title"):
            return self._answer("TITLE: A Ledger\nAUTHOR: Ned Rook, who keeps the stall\nPEOPLE: Ann, Bob, Cy\nSETTING: a shop")
        if user.startswith("Write the opening") or user.startswith("Write the closing") or user.startswith("Write a passage"):
            return self._answer("<pad>The rent fell due and the yard wanted sweeping.</pad>")
        n = re.match(r"Piece (F\d+):", user).group(1)
        names = " and ".join(compose.brew_names(self.items[n]))
        return self._answer(f"<piece>Here is piece {n} of the ledger{': ' + names if names else ''}.</piece>")

    @staticmethod
    def _answer(content):
        return SimpleNamespace(content=content, reasoning="", finish_reason="stop", usage={}, seconds=0.0)


def test_write_sheet_piece_by_piece(tmp_path, monkeypatch):
    monkeypatch.setattr(texts, "TEXTS_DIR", tmp_path / "texts")
    monkeypatch.setattr(write, "_example", lambda sheet: None)
    sheet = SHEETS["pamphlet:mint:13"]
    model = FakeModel(items(sheet))
    log = (tmp_path / "log.jsonl").open("w")
    assert write.write_sheet(sheet, model, model, model, 3, log)
    log.close()
    text = texts.path_of(sheet["id"]).read_text()
    assert text.startswith("Title: A Ledger\nAuthor: Ned Rook, who keeps the stall\nKind: merchant pamphlet\n\n")
    assert all(f"piece {i['n']}" in text for i in items(sheet)) and text.count("* ") == len(items(sheet))
    assert (texts.folder_of(sheet["id"]) / "metadata.json").exists()
    records = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    f2 = [r for r in records if r["part"] == "F2" and r["role"] == "writer"]
    assert len(f2) == 2                                    # misread once alone, so written again
    assert any(r["part"] == "whole" for r in records)


def test_a_piece_that_never_passes_fails_the_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(texts, "TEXTS_DIR", tmp_path / "texts")
    monkeypatch.setattr(write, "_example", lambda sheet: None)
    sheet = SHEETS["pamphlet:mint:13"]
    model = FakeModel(items(sheet))
    model.misread = set()
    original = model.complete

    def stubborn(messages, seed):                         # F1 always names a place the sheet does not use
        answer = original(messages, seed)
        if messages[-1]["content"].startswith("Piece F1:"):
            answer.content = answer.content.replace("Here is", "At Ludding is")
        return answer

    model.complete = stubborn
    log = (tmp_path / "log.jsonl").open("w")
    assert not write.write_sheet(sheet, model, model, model, 2, log)
    failed_text, failed_problems = texts.failed_of(sheet["id"])
    assert any("names that this text must not use" in p for p in json.loads(failed_problems.read_text()))
    assert not texts.path_of(sheet["id"]).exists()
