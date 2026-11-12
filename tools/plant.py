"""Plant action: {"action": "plant", "plots": {"3": {"plant": "sage", "soil": "yellow"}, "4": {"plant": "mint", "soil": "black"}}}."""

from environment.world import World
from tools.base import ToolError, ToolResult, require_dict, require_int


def run(world: World, args: dict) -> ToolResult:
    raw = require_dict(args, "plots")
    assignments = {}
    for plot, spec in raw.items():
        if not (isinstance(spec, dict) and isinstance(spec.get("plant"), str) and isinstance(spec.get("soil"), str)):
            raise ToolError(f'Plot {plot} needs a plant and a soil, e.g. {{"plant": "sage", "soil": "yellow"}}.')
        assignments[require_int(plot, "A plot number")] = (spec["plant"], spec["soil"])
    result = world.plant(assignments)
    planted = ", ".join(f"plot {p} ({plant}, {soil})" for p, (plant, soil) in result.planted.items()) or "nothing"
    text = f"Planted: {planted}."
    if result.failed:
        text += " Failed: " + ", ".join(f"plot {p} ({why})" for p, why in result.failed.items()) + "."
    return ToolResult(text, ends_turn=True)
