import json

import pytest

import main as main_module
from agents.random_agent import RandomAgent, _numbers
from main import main

BASE = ["--env-seed", "3", "--llm-seed", "5", "--turn-cap", "40", "--garden-size", "6",
        "--goals", "target:D:5,time:I:15", "--allergy", "mint+sage"]


def run_args(tmp_path, name):
    return BASE + ["--runs-dir", str(tmp_path / name / "runs"), "--temp-dir", str(tmp_path / name / "temp")]


def read(path):
    return path.read_text(encoding="utf-8")


def test_numbers_parses_garden_line():
    line = "Garden: free: 1, 10; growing: 3 (elderberry, 2 turns left), 4; ready: 7 (waiting 2), 8 (chamomile, waiting 0)"
    assert _numbers(line, "free") == [1, 10]
    assert _numbers(line, "growing") == [3, 4]
    assert _numbers(line, "ready") == [7, 8]
    assert _numbers("Garden: free: none; growing: none; ready: none", "free") == []


def test_full_episode_writes_all_outputs(tmp_path):
    out = main(run_args(tmp_path, "a"))
    for name in ("params.json", "transcript.md", "actions.jsonl", "ledger.jsonl", "final_state.json", "summary.json"):
        assert (out.dir / name).is_file()
    transcript = read(out.dir / "transcript.md")
    assert "My garden has 6 plots. I am allergic to the combination of mint and sage" in transcript
    assert "## Turn 40" in transcript and "## Turn 41" not in transcript
    assert json.loads(read(out.dir / "summary.json"))["turns_played"] == 40
    assert (out.temp / "checkpoint.json").is_file()


def test_crash_and_resume_matches_uninterrupted_run(tmp_path, monkeypatch):
    reference = main(run_args(tmp_path, "ref"))
    crash_at = len(read(reference.dir / "actions.jsonl").splitlines()) // 2   # halfway through the run
    assert crash_at > 5

    calls = {"n": 0}

    class CrashingAgent(RandomAgent):
        def _reply(self):
            calls["n"] += 1
            if calls["n"] == crash_at:
                raise ConnectionError("simulated crash mid-turn")
            return super()._reply()

    monkeypatch.setattr(main_module, "RandomAgent", CrashingAgent)
    with pytest.raises(ConnectionError):
        main(run_args(tmp_path, "crash"))
    run_dir = next((tmp_path / "crash" / "runs" / "random").iterdir())

    monkeypatch.setattr(main_module, "RandomAgent", RandomAgent)
    resumed = main(["--resume", str(run_dir)])

    for name in ("final_state.json", "summary.json", "actions.jsonl", "ledger.jsonl"):
        assert read(resumed.dir / name) == read(reference.dir / name), name
    # transcripts differ only in the title line (run id)
    assert read(resumed.dir / "transcript.md").split("\n", 1)[1] == read(reference.dir / "transcript.md").split("\n", 1)[1]


def test_resume_without_checkpoint_fails(tmp_path):
    out = main(run_args(tmp_path, "b"))
    (out.temp / "checkpoint.json").unlink()
    with pytest.raises(FileNotFoundError, match="No checkpoint"):
        main(["--resume", str(out.dir)])
