import json
import re
from pathlib import Path

from environment.brewer import PLANTS, STAT_SETS

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "system.txt"


def plant_groups(value):
    """Every dict or list in a JSON value whose keys or items are plant names."""
    if isinstance(value, dict):
        if value and set(value) <= set(PLANTS):
            yield set(value)
        for v in value.values():
            yield from plant_groups(v)
    elif isinstance(value, list):
        if value and all(v in PLANTS for v in value if isinstance(v, str)) and all(isinstance(v, str) for v in value):
            yield set(value)
        for v in value:
            yield from plant_groups(v)


def test_prompt_examples_do_not_leak_a_stat_plant_set():
    decoder = json.JSONDecoder()
    text = PROMPT.read_text(encoding="utf-8")
    groups = []
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        groups.extend(plant_groups(value))
    assert groups, "expected JSON examples in the prompt"
    for group in groups:
        for stat, plants in STAT_SETS.items():
            assert not set(plants) <= group, f"example {sorted(group)} contains the {stat} set"
