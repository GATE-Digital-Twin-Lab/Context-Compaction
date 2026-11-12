"""Free tool: {"tool": "gather"}. Collects all ready plots and clears dead plants; never fails and costs no turn."""

from environment.world import World
from tools.base import ToolResult


def run(world: World, args: dict) -> ToolResult:
    result = world.gather()
    if not result.plots:
        return ToolResult("Gathered nothing.")
    items = ", ".join(f"+{n} {plant}" for plant, n in result.counts.items())
    text = f"Gathered: {items}." if items else "Gathered nothing."
    if result.cleared:
        text += f" Cleared dead plants: {', '.join(map(str, result.cleared))}."
    return ToolResult(f"{text} Plots now free: {', '.join(map(str, result.plots))}.")
