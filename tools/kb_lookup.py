"""Free tool: {"tool": "kb_lookup", "plants": ["chamomile", "rosemary"]}."""

from environment.world import World
from tools.base import ToolError, ToolResult, turns


def run(world: World, args: dict) -> ToolResult:
    plants = args.get("plants")
    if not isinstance(plants, list) or not plants:
        raise ToolError('"plants" must be a non-empty list of plant names.')
    catalogue = world.kb.catalogue()
    if unknown := [p for p in plants if p not in catalogue]:
        raise ToolError(f"Unknown plant {unknown[0]}.")
    lines = []
    for plant in plants:
        growth, outcomes = world.lookup(plant)
        grows = f"grows in {turns(growth)}" if growth is not None else "growth time unknown"
        known = "; ".join(o.render() for o in outcomes) or "none"
        line = f"{plant}: {grows}. Interactions: {known}."
        if world.lore:
            line += " Lore: " + (" ".join(world.kb.lore(plant)) or "none yet.")
        lines.append(line)
    return ToolResult("\n".join(lines))
