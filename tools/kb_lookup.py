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
    plants = list(dict.fromkeys(plants))
    growth = world.kb.growth_times()
    grows = ", ".join(f"{p} {turns(growth[p])}" if p in growth else f"{p} unknown" for p in plants)
    sections = [f"Growth: {grows}.", _listed("Interactions", [o.render() for o in world.kb.outcomes(*plants)], "none.")]
    if world.lore:
        sections.append(_listed("Lore", world.kb.lore(*plants), "none yet."))
    return ToolResult("\n".join(sections))


def _listed(title: str, items: list[str], empty: str) -> str:
    """'Title: none.' or the title followed by one '- item' line per item (each shown once)."""
    if not items:
        return f"{title}: {empty}"
    return "\n".join([f"{title}:"] + [f"- {item}" for item in items])
