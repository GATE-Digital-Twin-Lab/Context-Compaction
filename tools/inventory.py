"""Free tool: {"tool": "inventory"}. Held potions are shown by id only; used-up potions are left out."""

from environment.world import World
from tools.base import ToolResult


def run(world: World, args: dict) -> ToolResult:
    inv = world.inventory
    plants = ", ".join(f"{p}: {n}" for p, n in sorted(inv.plants.items())) or "none"
    potions = ", ".join(f"#{p.id}" for p in inv.held) or "none"
    return ToolResult(f"plants: {plants}; potions: {potions}")
