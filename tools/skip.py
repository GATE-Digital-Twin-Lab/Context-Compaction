"""Skip action: {"action": "skip"}."""

from environment.world import World
from tools.base import ToolResult


def run(world: World, args: dict) -> ToolResult:
    world.skip()
    return ToolResult("Skipped.", ends_turn=True)
