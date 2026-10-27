"""Free tool: {"tool": "inventory"}. Potions are shown by id only."""

from environment.world import World
from tools.base import ToolResult


def run(world: World, args: dict) -> ToolResult:
    inv = world.inventory
    plants = ", ".join(f"{p}: {n}" for p, n in sorted(inv.plants.items())) or "none"
    potions = ", ".join(f"#{p.id}" + (" (logged)" if p.logged else "") for p in inv.potions) or "none"
    return ToolResult(f"plants: {plants}; potions: {potions}")
