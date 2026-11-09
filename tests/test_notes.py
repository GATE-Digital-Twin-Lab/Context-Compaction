import json

from LLM.notes import ORDER, SCHEMA, Item, main, parse_notes
from test_llm import run_llm_episode
from LLM.client import Completion

FULL = """Results:
  Potions:
  - #3 {"mint": 2, "dill": 1, "basil": 1} → none
  Growth:
  - none
  Lore:
  - none
State:
  Garden:
  - plot 1: mint, planted turn 4
  - plot 2: dill, planted turn 4,
    ready at turn 7
  Inventory:
  - none
  Logged:
  - none
  Best:
  - none
Beliefs:
  Confirmed:
  - none
  Hypotheses:
  - mint may matter (hypothesis)
  Refuted:
  - none
Plan:
  Next:
  - plant, to keep every plot growing
  Then:
  - brew when ready
  - log the brew
{"action": "skip"}
Results: written after the call is ignored"""


def test_a_reply_in_the_schema():
    notes = parse_notes(FULL)
    assert notes.valid and not notes.missing and not notes.problems
    assert notes.items[0] == Item("Results", "Potions", '#3 {"mint": 2, "dill": 1, "basil": 1} → none')
    assert notes.items[2].text == "plot 2: dill, planted turn 4, ready at turn 7"   # a wrapped line
    grouped = notes.grouped()
    assert grouped["Plan"]["Then"] == ["brew when ready", "log the brew"] and grouped["State"]["Inventory"] == []
    assert set(notes.empty) == {sub for _, sub in ORDER} - {"Potions", "Garden", "Hypotheses", "Next", "Then"}
    assert [sub for _, subs in SCHEMA.items() for sub in subs] == [sub for _, sub in ORDER]


def test_departures_from_the_schema():
    notes = parse_notes("**Results:**\n**Potions:** - #1 → +S 2%\nNew facts: something\n"
                        "Next:\n- brew\nGrowth:\n- mint 3\n- stray\nPotions:\n- again\n{\"tool\": \"gather\"}")
    assert not notes.valid
    assert notes.items[0] == Item("Results", "Potions", "#1 → +S 2%")
    assert Item("Plan", "Next", "brew") in notes.items and Item("Results", "Growth", "mint 3") in notes.items
    assert "Next outside Plan" in notes.problems and "Growth outside Results" in notes.problems
    assert "Potions written twice" in notes.problems and "sub-sections out of order" in notes.problems
    assert "not in the schema: 'New facts: something'" in notes.problems
    assert "Lore" in notes.missing and "Then" in notes.missing
    assert parse_notes("- loose line").problems == ["line outside any sub-section: 'loose line'"]
    assert parse_notes("Plan: go\nNext:\n- x").problems == ["text on the Plan heading: 'go'"]


def test_notes_are_written_for_every_reply(tmp_path, monkeypatch):
    def agent(messages, seed):
        return Completion(FULL, "thinking", "stop", {"prompt_tokens": 1}, 0.0)

    out = run_llm_episode(tmp_path, monkeypatch, agent, turn_cap="2")
    records = [json.loads(line) for line in (out.dir / "notes.jsonl").read_text().splitlines()]
    assert [r["turn"] for r in records] == [1, 2] and all(r["valid"] for r in records)
    assert records[0]["items"][0]["sub"] == "Potions"
    main([str(out.dir)])
    assert len((out.dir / "notes.jsonl").read_text().splitlines()) == 2
