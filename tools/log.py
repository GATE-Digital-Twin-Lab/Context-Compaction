"""Log action: {"action": "log", "potions": [{"id": 3, "labels": {"chamomile": "higher"}}]}."""

from environment.knowledge_base import LogError
from environment.world import World
from tools.base import ToolError, ToolResult, require_int


def run(world: World, args: dict) -> ToolResult:
    raw = args.get("potions")
    if not isinstance(raw, list) or not raw:
        raise ToolError('"potions" must be a non-empty list.')
    potions = {}
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("labels", {}), dict):
            raise ToolError('Each potion entry needs an "id" and an optional "labels" object.')
        potions[require_int(entry.get("id"), "A potion id")] = entry.get("labels", {})
    try:
        result = world.log(potions)
    except LogError as err:
        raise ToolError(str(err)) from None

    parts = []
    for log in result:
        text = f"potion #{log.potion_id}: " + (log.outcome.render() if log.new else "already known")
        if log.new_lore:
            text += " (the old herbals hold new lore about its plants: read it with kb_lookup)"
        parts.append(text)
    return ToolResult("Logged: " + ("; ".join(parts) if parts else "nothing new") + ".", ends_turn=True)
