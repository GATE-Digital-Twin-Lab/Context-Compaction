import json
import re

import pytest

import compaction.atomizer as atomizer
from LLM.client import Completion
from test_llm import FakeClient, run_llm_episode


def skipping_agent(messages, seed):
    return Completion(f"Turn noted {seed}.\n" + '{"action": "skip"}', "secret thinking", "stop", {"prompt_tokens": 1}, 0.0)


def test_parse_atoms():
    reply = 'Sure:\n{"atoms": [{"message": 2, "kind": "state", "text": " Plots 1-4 are free. "}]}'
    assert atomizer.parse_atoms(reply, 2) == [(2, "state", "Plots 1-4 are free.")]
    for bad in ("no json", '{"atoms": [{"message": 3, "kind": "state", "text": "x"}]}',
                '{"atoms": [{"message": 1, "kind": "score", "text": "x"}]}',
                '{"atoms": [{"message": 1, "kind": "plan", "text": ""}]}', '{"atoms": [{"message": 1,'):
        with pytest.raises(ValueError):
            atomizer.parse_atoms(bad, 2)


def covering_reply(messages, seed):
    """One atom per numbered message of the request (the last one is a plan)."""
    count = len(re.findall(r"^\[\d+\] \w+ \(turn \d+\):$", messages[1]["content"].split("<messages>")[1], re.M))
    atoms = [{"message": n, "kind": "state", "text": f"Fact {n} from seed {seed}."} for n in range(1, count)]
    atoms.append({"message": count, "kind": "plan", "text": "The agent waits."})
    return Completion(json.dumps({"atoms": atoms}), "", "stop", {"prompt_tokens": 3}, 0.1)


def test_atomize_run(tmp_path, monkeypatch):
    run = run_llm_episode(tmp_path, monkeypatch, skipping_agent, turn_cap="3").dir
    requests = []

    class Client(FakeClient):
        def __init__(self, *args, **kwargs):
            super().__init__([])
            self.temperature = None

        def complete(self, messages, seed):
            requests.append((messages, seed, self.temperature))
            if len(requests) == 2:   # turn 2: one malformed reply, then a valid one
                return Completion("not json", "", "stop", {}, 0.0)
            return covering_reply(messages, seed)

    monkeypatch.setattr(atomizer, "ChatClient", Client)
    atoms = atomizer.main([str(run), "--seed", "100"])

    assert [(r[1], r[2]) for r in requests] == [(101, 0.0), (102, 0.0), (103, 0.7), (103, 0.0)]
    first = requests[0][0][1]["content"]
    assert "SYSTEM PROMPT" in first and "<context>" not in first and "[1] user (turn 1):" in first
    second = requests[1][0][1]["content"]
    assert "<context>\nuser (turn 1):" in second and "[1] environment (turn 2):" in second
    assert "secret thinking" not in json.dumps(requests)
    assert requests[0][0][0]["content"] == atomizer.ATOMIZE_PROMPT.read_text().strip()

    assert atoms[0].id == "a0001" and atoms[0].role == "user" and atoms[0].turn == 1
    turn2 = [a for a in atoms if a.turn == 2]
    assert turn2[0].text == "Fact 1 from seed 103." and turn2[-1].role == "environment"
    lines = (run / "atoms.jsonl").read_text().splitlines()
    assert json.loads(lines[-1]) == {"id": f"a{len(atoms):04d}", "turn": 3, "message": atoms[-1].message,
                                     "role": atoms[-1].role, "kind": "plan", "text": "The agent waits."}
    calls = [json.loads(line) for line in (run / "atoms_calls.jsonl").read_text().splitlines()]
    assert calls[0]["settings"]["thinking"] is False and calls[0]["settings"]["temperature"] == 0.0 and len(calls) == 4
    assert calls[2]["attempts"][0]["error"] == "no JSON object in the reply" and len(calls[2]["attempts"]) == 2
    assert not any("incomplete" in c for c in calls[1:])
    md = (run / "atoms.md").read_text()
    assert "## Turn 2" in md and f"- `{turn2[0].id}` *state*: Fact 1 from seed 103." in md


def test_uncovered():
    target = [atomizer.Message(1, 1, "environment", "Interactions:\n- a, b → none\n- c, d → +S"),
              atomizer.Message(2, 1, "environment", "Skipped."),
              atomizer.Message(3, 1, "agent", "A long enough message that says something.")]
    assert atomizer.uncovered(target, []) == [1, 3]
    assert atomizer.uncovered(target, [(1, "observation", "x"), (3, "plan", "y")]) == [1]
    assert atomizer.uncovered(target, [(1, "observation", "x"), (1, "observation", "y"), (3, "plan", "z")]) == []


def test_incomplete_replies_are_retried_and_the_best_is_kept(tmp_path, monkeypatch):
    run = run_llm_episode(tmp_path, monkeypatch, skipping_agent, turn_cap="3").dir
    replies = []

    class Client(FakeClient):
        def __init__(self, *args, **kwargs):
            super().__init__([])

        def complete(self, messages, seed):
            replies.append(seed)
            if len(replies) == 1:
                return Completion('{"atoms": []}', "", "stop", {}, 0.0)   # empty: covers nothing
            full = json.loads(covering_reply(messages, seed).content)["atoms"]
            return Completion(json.dumps({"atoms": full[1:]}), "", "stop", {}, 0.0)   # misses message 1

    monkeypatch.setattr(atomizer, "ChatClient", Client)
    atoms = atomizer.main([str(run), "--turns", "2"])
    assert replies == [2, 3, 4] and atoms and all(a.turn == 2 for a in atoms)
    call = [json.loads(line) for line in (run / "atoms_calls.jsonl").read_text().splitlines()][1]
    first_message = call["messages"][0]
    assert call["incomplete"] == [first_message] and "error" not in call
    assert len(call["attempts"][0]["uncovered"]) > len(call["attempts"][1]["uncovered"])
    assert f"(message {first_message}) — not fully covered by its atoms" in (run / "atoms.md").read_text()


def test_atomize_selected_turns_and_failures(tmp_path, monkeypatch):
    run = run_llm_episode(tmp_path, monkeypatch, skipping_agent, turn_cap="3").dir

    class Client(FakeClient):
        def __init__(self, *args, **kwargs):
            super().__init__([])

        def complete(self, messages, seed):
            return Completion("never json", "", "stop", {}, 0.0)

    monkeypatch.setattr(atomizer, "ChatClient", Client)
    assert atomizer.main([str(run), "--turns", "2"]) == []
    md = (run / "atoms.md").read_text()
    assert "## Turn 2 (atomizer failed)" in md and "## Turn 1" not in md and "## Turn 3" not in md
    calls = [json.loads(line) for line in (run / "atoms_calls.jsonl").read_text().splitlines()]
    assert calls[1]["error"] == "no valid reply" and len(calls[1]["attempts"]) == atomizer.ATTEMPTS
