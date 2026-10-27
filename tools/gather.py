"""Gather action: {"action": "gather"}. Collects all ready plots; never fails."""

from environment.world import World
from tools.base import ToolResult


def run(world: World, args: dict) -> ToolResult:
    counts = world.gather().counts
    if not counts:
        return ToolResult("Gathered nothing.", ends_turn=True)
    items = ", ".join(f"+{n} {plant}" for plant, n in counts.items())
    return ToolResult(f"Gathered: {items}.", ends_turn=True)
