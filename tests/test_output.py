import json

import pytest

from environment.brewer import PLANTS

from environment.world import World
from input import parse_args
from ledger import Ledger
from output import RunOutput
from tools.dispatcher import Dispatcher


@pytest.fixture
def config(tmp_path):
    return parse_args([
        "--runs-dir", str(tmp_path / "runs"), "--temp-dir", str(tmp_path / "temp"),
        "--env-seed", "1", "--goals", "target:S:10,time:I:5", "--turn-cap", "3",
    ])


def make_world(config, out):
    return World.create(
        config.garden_size, (config.growth_min, config.growth_max), list(config.goals),
        config.allergy, config.turn_cap, config.env_seed, kb_path=str(out.kb_path),
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_folders_and_params(config):
    out = RunOutput(config, rid="20261027-120000-abcd")
    assert out.dir == config.runs_dir / "random" / "20261027-120000-abcd"
    assert (out.dir / "compactions").is_dir() and out.temp.is_dir()
    out.write_params(config, {"growth_times": {"mint": 3}})
    params = json.loads((out.dir / "params.json").read_text(encoding="utf-8"))
    assert params["run_id"] == "20261027-120000-abcd"
    assert params["goals"][0] == {"kind": "target", "stat": "S", "turns": None, "target": 10}
    assert params["growth_times"] == {"mint": 3}


def test_summary_after_turn_cap(config):
    out = RunOutput(config)
    world = make_world(config, out)
    for _ in range(3):                      # turn cap 3: goal 1 fails, goal 2 never starts
        world.skip()
        world.end_turn()
    out.write_final(world)
    summary = json.loads((out.dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["episode_over"] and summary["turns_played"] == 3
    assert not summary["goals"][0]["success"] and summary["goal_in_progress"] is None
    assert [g["stat"] for g in summary["goals_not_started"]] == ["I"]
    world.kb.close()


def test_same_run_id_twice_is_refused(config):
    RunOutput(config, rid="x")
    with pytest.raises(FileExistsError):
        RunOutput(config, rid="x")


def test_logs_and_final_files(config):
    out = RunOutput(config)
    world = make_world(config, out)
    d, ledger = Dispatcher(world), Ledger()
    out.log_facts(ledger.observe(world))

    world.inventory.add_plants({"mint": 2, "chamomile": 3, "rosemary": 2})
    call = {"action": "brew", "recipe": {"mint": 2, "chamomile": 3, "rosemary": 2}}
    out.log_message(world.turn, "environment", "[Turn 1]\nGarden: ...")
    out.log_message(world.turn, "agent", "I will brew strength.")
    result = d.handle(call)
    out.log_call(world.turn, call, result)
    world.end_turn()
    out.log_facts(ledger.observe(world))
    out.write_final(world)

    actions = read_jsonl(out.dir / "actions.jsonl")
    assert actions == [{"turn": 1, "call": call, "text": result.text, "ends_turn": True, "error": False}]

    facts = read_jsonl(out.dir / "ledger.jsonl")
    assert facts[0]["kind"] == "goal" and any(f["id"] == "potion:1" for f in facts)

    transcript = (out.dir / "transcript.md").read_text(encoding="utf-8")
    assert transcript.count("## Turn 1") == 1 and "**agent**\n\nI will brew strength." in transcript

    summary = json.loads((out.dir / "summary.json").read_text(encoding="utf-8"))
    first = summary["goals"][0]
    assert first["success"] and first["best_intensity"] == 10 and first["best_potion"]["id"] == 1
    assert not summary["episode_over"]
    assert summary["goal_in_progress"]["stat"] == "I" and summary["goals_not_started"] == []

    state = json.loads((out.dir / "final_state.json").read_text(encoding="utf-8"))
    assert state["inventory"]["potions"][0]["effect"] == {"positive": {"S": 10}, "negative": {}}
    assert set(state["garden"]["growth_times"]) == set(PLANTS)
    assert out.kb_path.is_file()
    world.kb.close()
