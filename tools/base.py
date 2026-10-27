"""Shared types for agent-facing tools."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    text: str
    ends_turn: bool = False  # True for actions (they cost the turn)
    error: bool = False


class ToolError(Exception):
    """A failed call: costs no turn, counts toward the failure limit."""


def turns(n: int) -> str:
    """'1 turn', '4 turns'."""
    return f"{n} turn" if n == 1 else f"{n} turns"


def require_dict(args: dict[str, Any], key: str) -> dict:
    value = args.get(key)
    if not isinstance(value, dict):
        raise ToolError(f'"{key}" must be an object.')
    return value


def require_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            return int(str(value))
        except ValueError:
            raise ToolError(f"{what} must be a whole number, got {value!r}.") from None
    return value
