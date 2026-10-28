"""Finds the agent's call in its reply and cuts off anything written after it."""

import json

_decoder = json.JSONDecoder()


def extract_call(text: str) -> tuple[str | dict, str]:
    """(call, kept text). The call is the first JSON object with "action" or "tool", else the first
    JSON object, else the raw text (the dispatcher reports it). The kept text ends right after the
    call, so results the model invents after it never enter the conversation."""
    first: tuple[dict, int] | None = None
    i = text.find("{")
    while i != -1:
        try:
            value, end = _decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        if isinstance(value, dict):
            if "action" in value or "tool" in value:
                return value, _cut(text, end)
            first = first or (value, end)
        i = text.find("{", end)
    if first is not None:
        return first[0], _cut(text, first[1])
    return text.strip(), text.strip()


def _cut(text: str, end: int) -> str:
    kept = text[:end].rstrip()
    if kept.count("```") % 2 == 1:  # the call sat inside a code fence: close it
        kept += "\n```"
    return kept
