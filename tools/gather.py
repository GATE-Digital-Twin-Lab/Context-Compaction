"""Free tool: {"tool": "gather"}. Collects all ready plots; never fails and costs no turn."""

from environment.world import World
from tools.base import ToolResult


def run(world: World, args: dict) -> ToolResult:
    result = world.gather()
    if not result.counts:
        return ToolResult("Gathered nothing.")
    items = ", ".join(f"+{n} {plant}" for plant, n in result.counts.items())
    return ToolResult(f"Gathered: {items}. Plots now free: {', '.join(map(str, result.plots))}.")
