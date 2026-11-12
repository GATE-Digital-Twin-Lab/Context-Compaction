"""Deliver action: {"action": "deliver", "potion": 12}. Ends the request; the agent gets no feedback
on success."""

from environment.world import DeliveryError, World
from tools.base import ToolError, ToolResult, require_int


def run(world: World, args: dict) -> ToolResult:
    pid = require_int(args.get("potion"), '"potion"')
    try:
        world.deliver(pid)
    except DeliveryError as err:
        raise ToolError(f"{err} Nothing was delivered.") from None
    return ToolResult(f"Delivered potion #{pid}. The request is closed.", ends_turn=True)
