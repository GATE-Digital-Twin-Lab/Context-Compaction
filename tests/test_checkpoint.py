import json

import pytest

import checkpoint
from environment.goals import Allergy, Goal, GoalKind
from environment.world import World
from input import ExperimentConfig, parse_args, parse_command
from ledger import Ledger
from output import RunOutput
from tools.dispatcher import Dispatcher

GROWTH = {"mint": 3, "elderberry": 4, "nettle": 3, "sage": 2, "chamomile": 3, "dill": 3, "basil": 6, "rosemary": 3}
CALLS = [
    {"action": "plant", "plots": {"1": "sage", "2": "basil", "3": "elderberry"}},
    {"action": "skip"},
    {"action": "log", "garden": True},
    {"tool": "gather"},
    {"action": "brew", "recipe": {"mint": 2, "chamomile": 3, "rosemary": 2}},   # reaches the S target
    {"action": "log", "potions": [{"id": 1, "labels": {"chamomile": "higher"}}]},
]
MORE = [{"action": "plant", "plots": {"4": "mint"}}, {"action": "skip"}, {"tool": "gather"}]


def new_world(kb_path=":memory:") -> World:
    goals = [Goal(GoalKind.TARGET, "S", target=10), Goal(GoalKind.TIME, "I", turns=20)]
    world = World.create(7, (2, 6), goals, Allergy(frozenset({"nettle", "chamomile"})), 100, seed=0, kb_path=kb_path)
    world.garden.growth_times = dict(GROWTH)
    world.inventory.add_plants({"mint": 4, "chamomile": 3, "rosemary": 2})
    return world


def play(world, ledger, calls):
    d = Dispatcher(world)
    texts = []
    for call in calls:
        result = d.handle(call)
        texts.append(result.text)
        if result.ends_turn:
            world.end_turn()
        ledger.observe(world)
    return texts


def test_world_and_ledger_round_trip_then_continue_identically():
    world, ledger = new_world(), Ledger()
    ledger.observe(world)
    play(world, ledger, CALLS)
    data = json.loads(json.dumps({"world": world.to_dict(), "ledger": ledger.to_dict()}))
    copy, copy_ledger = World.from_dict(data["world"]), Ledger.from_dict(data["ledger"])
    assert copy.to_dict() == world.to_dict()
    assert copy.view() == world.view() and copy.results == world.results
    assert play(copy, copy_ledger, MORE) == play(world, ledger, MORE)
    assert copy.to_dict() == world.to_dict()
    assert copy_ledger.snapshot(copy) == ledger.snapshot(world)


def test_crash_mid_turn_restores_last_checkpoint(tmp_path):
    config = parse_args(["--runs-dir", str(tmp_path / "r"), "--temp-dir", str(tmp_path / "t"), "--env-seed", "0"])
    out = RunOutput(config)
    world, ledger = new_world(str(out.kb_path)), Ledger()
    out.log_facts(ledger.observe(world))
    play(world, ledger, CALLS)
    out.log_message(world.turn, "agent", "completed turn")
    checkpoint.save(out.temp, out.dir, world, ledger, {"messages": ["m1"]}, compactions=0)
    saved = world.to_dict()

    # a turn that crashes halfway: KB written, logs appended, a compaction file created
    world.kb.log_outcome({"mint": "odd", "chamomile": "present", "rosemary": "present"}, "+S", 1, world.turn)
    out.log_message(world.turn, "agent", "half a turn")
    out.log_call(world.turn, {"action": "skip"}, Dispatcher(world).handle({"tool": "inventory"}))
    out.write_compaction(1, {"partial": True})
    world.kb.close()

    cp = checkpoint.load(out.temp)
    restored, restored_ledger = checkpoint.restore(cp, out.dir, out.kb_path)
    assert restored.to_dict() == saved                          # KB file rebuilt from the checkpoint
    assert cp.agent == {"messages": ["m1"]}
    assert "half a turn" not in (out.dir / "transcript.md").read_text(encoding="utf-8")
    assert not (out.dir / "actions.jsonl").exists() or (out.dir / "actions.jsonl").read_text() == ""
    assert list((out.dir / "compactions").glob("*.json")) == []
    assert not (out.temp / "checkpoint.json.tmp").exists()
    restored.kb.close()


def test_load_without_checkpoint(tmp_path):
    assert checkpoint.load(tmp_path) is None


def test_resume_command(tmp_path):
    config = parse_args(["--runs-dir", str(tmp_path / "r"), "--temp-dir", str(tmp_path / "t"),
                         "--goals", "time:S:30", "--allergy", "nettle+chamomile", "--env-seed", "4"])
    out = RunOutput(config)
    out.write_params(config, {"growth_times": GROWTH})
    resumed, run_dir = parse_command(["--resume", str(out.dir)])
    assert run_dir == out.dir and resumed == config
    assert RunOutput.reopen(resumed, out.dir).temp == out.temp


def test_resume_rejects_other_options(tmp_path, capsys):
    with pytest.raises(SystemExit):
        parse_command(["--resume", str(tmp_path), "--garden-size", "5"])
    assert "--resume takes no other options" in capsys.readouterr().err


def test_resume_without_params(tmp_path, capsys):
    with pytest.raises(SystemExit):
        parse_command(["--resume", str(tmp_path)])
    assert "No params.json" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--compaction-trigger", "0"], "--compaction-trigger"),
        (["--compaction-trigger", "1.5"], "--compaction-trigger"),
        (["--context-window", "0"], "--context-window"),
    ],
)
def test_compaction_arguments(argv, message, capsys):
    with pytest.raises(SystemExit):
        parse_args(argv)
    assert message in capsys.readouterr().err


def test_config_round_trip():
    config = parse_args(["--goals", "target:I:10", "--allergy", "nettle+chamomile", "--context-window", "8000"])
    assert ExperimentConfig.from_dict(json.loads(json.dumps(config.to_dict()))) == config
