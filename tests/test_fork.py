import json

import pytest

import compaction.fork as fork_module
from compaction.summary import summarise
from LLM.client import Completion
from test_llm import FakeClient, run_llm_episode
from utils import transcript_blocks

SUMMARY_REQUEST = "Your task is to write a detailed summary"


def skipping_agent(messages, seed):
    return Completion(f"Notes {seed}.\n" + '{"action": "skip"}', f"thinking {seed}", "stop", {"prompt_tokens": 1}, 0.0)


def test_summarise_keeps_the_last_messages_out_of_the_summary():
    client = FakeClient([("SUMMARY TEXT", "summary thinking")])
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    result = summarise(client, "SYSTEM", messages, seed=7, keep_last=1)
    request, seed = client.requests[0]
    assert seed == 7 and request[0] == {"role": "system", "content": "SYSTEM"}
    assert request[1:3] == messages[:2] and request[3]["content"].startswith(SUMMARY_REQUEST)
    assert result.summary == "SUMMARY TEXT" and result.summarised == messages[:2]
    assert "the most recent messages follow it unchanged" in result.after[0]["content"]
    assert "<summary>\nSUMMARY TEXT\n</summary>" in result.after[0]["content"]
    assert result.after[1:] == [{"role": "user", "content": "c"}]


def test_summarise_everything():
    client = FakeClient([("S", "")])
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    result = summarise(client, "SYSTEM", messages, seed=7)
    assert result.summarised == messages and len(result.after) == 1
    assert "replaces all earlier messages" in result.after[0]["content"]
    with pytest.raises(ValueError):
        summarise(client, "SYSTEM", messages, seed=7, keep_last=2)


def fork_with_fake_model(tmp_path, monkeypatch, *args):
    parent = run_llm_episode(tmp_path, monkeypatch, skipping_agent).dir
    requests = []

    class Client(FakeClient):
        def __init__(self, *args, **kwargs):
            super().__init__([])

        def complete(self, messages, seed):
            requests.append((messages, seed))
            if SUMMARY_REQUEST in messages[-1]["content"]:
                return Completion("Skipped every turn.", "summary thinking", "stop", {"prompt_tokens": 99}, 0.0)
            return skipping_agent(messages, seed)

    monkeypatch.setattr(fork_module, "ChatClient", Client)
    return parent, fork_module.main([str(parent), "--at", "3", *args]), requests


def test_fork_replays_compacts_and_continues(tmp_path, monkeypatch):
    parent, out, requests = fork_with_fake_model(tmp_path, monkeypatch, "--keep-turns", "0")

    assert out.dir == parent / "compactions" / "t003_summary"
    transcript = (out.dir / "transcript.md").read_text()
    original = (parent / "transcript.md").read_text()
    assert transcript.split("\n", 1)[1].startswith(original.split("\n", 1)[1].split("\n## Turn 4\n")[0])
    blocks = transcript_blocks(transcript)
    marker = [role for _, role, _ in blocks].index("compaction")
    assert blocks[marker][0] == 3 and "after turn 3" in blocks[marker][2] and "turns 1–3" in blocks[marker][2]
    assert "<summary>\nSkipped every turn.\n</summary>" in blocks[marker + 1][2]
    assert "## Turn 6" in transcript and "Episode" not in transcript

    # the first call after the fork sees only the summary and turn 4; seeds continue after the 3 replayed calls
    first, seed = requests[1]
    assert seed == 5 + 3 and len(first) == 2 and "Skipped every turn." in first[1]["content"]
    assert "[Turn 4]" in first[1]["content"] and "Notes 5." not in first[1]["content"]

    record = json.loads((out.dir / "compactions" / "001.json").read_text())
    assert record["turn"] == 3 and record["summary"] == "Skipped every turn."
    assert len(record["context_before"]) == len(record["summarised"]) == 1 + 3 * 3   # opening, then header, reply, result
    assert (out.dir / "compaction_summary.md").read_text() == "Skipped every turn.\n"
    params = json.loads((out.dir / "params.json").read_text())
    assert params["fork"] == {"parent": str(parent), "at_turn": 3, "compactor": "summary", "keep_turns": 0}
    clean = (out.dir / "transcript_clean.md").read_text()
    assert "**compaction**" in clean and "thinking 5" not in clean
    assert json.loads((out.dir / "summary.json").read_text())["turns_played"] == 6


def test_fork_keeps_the_last_turns_verbatim(tmp_path, monkeypatch):
    parent, out, requests = fork_with_fake_model(tmp_path, monkeypatch, "--keep-turns", "2", "--name", "k2")
    summary_request = requests[0][0]
    assert "[Turn 1]" in summary_request[1]["content"] and "[Turn 2]" not in json.dumps(summary_request)
    first = requests[1][0]
    assert "Skipped every turn." in first[1]["content"] and "[Turn 2]" in first[1]["content"]
    assert [m["role"] for m in first[1:]] == ["user", "assistant", "user", "assistant", "user"]   # turns 2, 3 and 4
    record = json.loads((out.dir / "compactions" / "001.json").read_text())
    assert len(record["summarised"]) == 1 + 3 and len(record["context_after"]) == 1 + 2 * 3
    marker = next(c for _, role, c in transcript_blocks((out.dir / "transcript.md").read_text()) if role == "compaction")
    assert "messages of turn 1 above" in marker and "Turns 2–3 stay in the context verbatim" in marker


def test_fork_rejects_keeping_every_turn(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="keep-turns"):
        fork_with_fake_model(tmp_path, monkeypatch, "--keep-turns", "3")
