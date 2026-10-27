"""Plant action: {"action": "plant", "plots": {"3": "p2", "4": "p7"}}."""

from environment.world import World
from tools.base import ToolError, ToolResult, require_dict, require_int


def run(world: World, args: dict) -> ToolResult:
    raw = require_dict(args, "plots")
    assignments = {}
    for plot, plant in raw.items():
        if not isinstance(plant, str):
            raise ToolError(f"Plant for plot {plot} must be a name like \"p2\".")
        assignments[require_int(plot, "A plot number")] = plant
    result = world.plant(assignments)
    planted = ", ".join(f"plot {p} ({plant})" for p, plant in result.planted.items()) or "nothing"
    text = f"Planted: {planted}."
    if result.failed:
        text += " Failed: " + ", ".join(f"plot {p} ({why})" for p, why in result.failed.items()) + "."
    return ToolResult(text, ends_turn=True)
