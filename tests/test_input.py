import json
import re
from datetime import datetime

import pytest

from environment.requests import Request
from input import ExperimentConfig, parse_args
from utils import run_id, slugify


def test_defaults_are_valid_and_seeds_recorded():
    config = parse_args([])
    assert config.agent == "random" and config.agent_label == "random"
    assert isinstance(config.env_seed, int) and isinstance(config.llm_seed, int)
    json.dumps(config.to_dict())  # params.json must be serialisable


def test_explicit_values():
    config = parse_args(["--garden-size", "8", "--env-seed", "7", "--request", "stonecutter", "--turn-cap", "90"])
    assert config.request.id == "stonecutter" and config.request.stat == "S" and config.request.threshold == 25
    assert (config.garden_size, config.env_seed, config.turn_cap) == (8, 7, 90)


def test_the_whole_request_is_stored_in_the_config(tmp_path):
    requests = tmp_path / "requests.json"
    requests.write_text(json.dumps([{"id": "fever", "text": "Help.", "stat": "D", "excluded": ["mint"]}]), encoding="utf-8")
    config = parse_args(["--request", "fever", "--requests-file", str(requests)])
    assert config.request == Request("fever", "Help.", "D", excluded=frozenset({"mint"}))
    assert ExperimentConfig.from_dict(json.loads(json.dumps(config.to_dict()))) == config


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--request", "nobody"], "Unknown request 'nobody'"),
        (["--requests-file", "missing.json"], "Requests file not found"),
        (["--agent", "llm"], "--llm-name is required"),
        (["--agent", "llm", "--llm-name", "m", "--prompt-file", "missing.txt"], "Prompt file not found"),
        (["--garden-size", "0"], "--garden-size"),
        (["--turn-cap", "0"], "--turn-cap"),
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
