"""Log action: {"action": "log", "garden": true, "potions": [{"id": 3, "labels": {"p5": "higher"}}]}."""

from environment.knowledge_base import LogError
from environment.world import World
from tools.base import ToolError, ToolResult, require_int, turns


def run(world: World, args: dict) -> ToolResult:
    garden = args.get("garden", False)
    if not isinstance(garden, bool):
        raise ToolError('"garden" must be true or false.')
    raw = args.get("potions", [])
    if not isinstance(raw, list):
        raise ToolError('"potions" must be a list.')
    if not garden and not raw:
        raise ToolError('Nothing to log: give "garden": true and/or "potions".')
    potions = {}
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("labels", {}), dict):
            raise ToolError('Each potion entry needs an "id" and an optional "labels" object.')
        potions[require_int(entry.get("id"), "A potion id")] = entry.get("labels", {})
    try:
        result = world.log(garden, potions)
    except LogError as err:
        raise ToolError(str(err)) from None

    parts = []
    if result.garden and result.garden.growth:
        parts.append("growth " + ", ".join(f"{p} = {turns(t)}" for p, t in result.garden.growth.items()))
    if result.garden and result.garden.plantings:
        parts.append("plantings: " + ", ".join(f"plot {n} ({p})" for n, p in result.garden.plantings.items()))
    for log in result.potions:
        parts.append(f"potion #{log.potion_id}: " + (log.outcome.render() if log.new else "already known"))
    return ToolResult("Logged: " + ("; ".join(parts) if parts else "nothing new") + ".", ends_turn=True)
