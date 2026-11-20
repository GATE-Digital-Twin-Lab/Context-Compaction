import json

import pytest

from environment.world import World
from input import parse_args
from ledger import Ledger
from output import RunOutput
from tools.dispatcher import Dispatcher


@pytest.fixture
def config(tmp_path):
    return parse_args([
        "--runs-dir", str(tmp_path / "runs"), "--temp-dir", str(tmp_path / "temp"),
        "--env-seed", "1", "--request", "stonecutter", "--turn-cap", "3",
    ])


def make_world(config, out):
    return World.create(
        config.garden_size, config.request, config.turn_cap, config.env_seed,
        config.corpus_seed, config.corpus_size,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_folders_and_params(config):
    out = RunOutput(config, rid="20261027-120000-abcd")
    assert out.dir == config.runs_dir / "random" / "20261027-120000-abcd"
    assert (out.dir / "compactions").is_dir() and out.temp.is_dir()
    out.write_params(config, {"soil_table": {"mint": {"brown": [2, 100]}}})
    params = json.loads((out.dir / "params.json").read_text(encoding="utf-8"))
    assert params["run_id"] == "20261027-120000-abcd"
    assert params["request"]["id"] == "stonecutter" and params["request"]["threshold"] == 25
    assert params["soil_table"] == {"mint": {"brown": [2, 100]}}


def test_summary_after_turn_cap(config):
    out = RunOutput(config)
    world = make_world(config, out)
    for _ in range(3):                      # turn cap 3, before the deadline (turn 70)
        world.skip()
        world.end_turn()
    out.write_final(world)
    summary = json.loads((out.dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["episode_over"] and summary["turns_played"] == 3
    assert summary["request"]["translation"] == "S >= +25% by day 7 (turn 70)" and summary["request"]["last_turn"] == 3
    assert summary["result"] == {"potion": None, "turn": 3, "success": False, "intensity": 0,
                                 "failures": ["nothing delivered"]}


def test_same_run_id_twice_is_refused(config):
    RunOutput(config, rid="x")
    with pytest.raises(FileExistsError):
        RunOutput(config, rid="x")


def test_logs_and_final_files(config):
    out = RunOutput(config)
    world = make_world(config, out)
    d, ledger = Dispatcher(world), Ledger()
    out.log_facts(ledger.observe(world))

    world.inventory.add_plants({"mint": 2, "chamomile": 4, "rosemary": 2, "basil": 1})
    call = {"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2, "basil": 1}}   # S 25 (fragrant)
    out.log_message(world.turn, "environment", "[Day 1, turn 1]\nGarden: ...")
    out.log_message(world.turn, "agent", "I will brew strength.")
    result = d.handle(call)
    out.log_call(world.turn, call, result)
    world.end_turn()
    out.log_facts(ledger.observe(world))
    deliver = {"action": "deliver", "potion": 1}
    out.log_call(world.turn, deliver, d.handle(deliver))
    world.end_turn()
    out.write_final(world)

    actions = read_jsonl(out.dir / "actions.jsonl")
    assert actions[0] == {"turn": 1, "call": call, "text": result.text, "ends_turn": True, "error": False}
    assert actions[1]["call"] == deliver and actions[1]["turn"] == 2

    facts = read_jsonl(out.dir / "ledger.jsonl")
    assert {f["id"] for f in facts} == {"potion:1", "best:#1"}

    transcript = (out.dir / "transcript.md").read_text(encoding="utf-8")
    assert transcript.count("## Turn 1") == 1 and "**agent**\n\nI will brew strength." in transcript

    summary = json.loads((out.dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["episode_over"] and summary["result"]["success"] and summary["result"]["intensity"] == 25
    assert summary["delivered_potion"]["id"] == 1 and summary["delivered_potion"]["used"]

    state = json.loads((out.dir / "final_state.json").read_text(encoding="utf-8"))
    assert state["inventory"]["potions"][0]["effect"] == {"positive": {"S": 25}, "negative": {}, "secondary": ["fragrant"]}
    assert state["garden"]["size"] == world.garden.size and state["garden"]["died"] == []
