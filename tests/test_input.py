import json
import re
from datetime import datetime

import pytest

from environment.goals import Goal, GoalKind
from input import parse_allergy, parse_args, parse_goal
from utils import run_id, slugify


def test_defaults_are_valid_and_seeds_recorded():
    config = parse_args([])
    assert config.agent == "random" and config.agent_label == "random"
    assert isinstance(config.env_seed, int) and isinstance(config.llm_seed, int)
    json.dumps(config.to_dict())  # params.json must be serialisable


def test_explicit_values():
    config = parse_args([
        "--garden-size", "8", "--growth-min", "3", "--growth-max", "5", "--env-seed", "7",
        "--goals", "time:S:30, target:i:10", "--allergy", "p3+p5", "--turn-cap", "90",
    ])
    assert config.goals == (Goal(GoalKind.TIME, "S", turns=30), Goal(GoalKind.TARGET, "I", target=10))
    assert config.to_dict()["allergy"] == ["p3", "p5"]
    assert (config.garden_size, config.growth_min, config.growth_max, config.env_seed) == (8, 3, 5, 7)


@pytest.mark.parametrize("text", ["time:S", "speed:S:10", "time:X:10", "target:S:abc", "time:S:0"])
def test_invalid_goals(text):
    with pytest.raises(ValueError):
        parse_goal(text)


def test_allergy_parsing():
    assert parse_allergy("none") is None
    assert parse_allergy("p5+p3").plants == {"p3", "p5"}
    with pytest.raises(ValueError):
        parse_allergy("p3")


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--goals", "target:S:10", "--allergy", "p1+p5"], "impossible"),
        (["--agent", "llm"], "--llm-name is required"),
        (["--agent", "llm", "--llm-name", "m", "--prompt-file", "missing.txt"], "Prompt file not found"),
        (["--garden-size", "0"], "--garden-size"),
        (["--growth-min", "5", "--growth-max", "2"], "--growth-min"),
        (["--turn-cap", "0"], "--turn-cap"),
        (["--goals", ""], "At least one goal"),
    ],
)
def test_invalid_arguments_exit_with_message(argv, message, capsys):
    with pytest.raises(SystemExit):
        parse_args(argv)
    assert message in capsys.readouterr().err


def test_llm_agent_label(tmp_path):
    prompt = tmp_path / "system.txt"
    prompt.write_text("hi")
    config = parse_args(["--agent", "llm", "--llm-name", "Qwen/Qwen3-8B", "--prompt-file", str(prompt)])
    assert config.agent_label == "Qwen_Qwen3-8B"


def test_utils():
    assert slugify("Qwen/Qwen3 8B:latest") == "Qwen_Qwen3_8B_latest"
    assert slugify("///") == "unnamed"
    rid = run_id(datetime(2026, 10, 27, 14, 35, 12))
    assert re.fullmatch(r"20261027-143512-[0-9a-f]{4}", rid)
