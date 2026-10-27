"""Brew action: {"action": "brew", "recipe": {"p1": 2, "p5": 4, "p8": 2}}."""

import json

from environment.brewer import RecipeError
from environment.world import InfeasibleBrew, World
from tools.base import ToolError, ToolResult, require_dict


def run(world: World, args: dict) -> ToolResult:
    recipe = require_dict(args, "recipe")
    try:
        potion = world.brew(recipe)
    except RecipeError as err:
        raise ToolError(str(err)) from None
    except InfeasibleBrew as err:
        missing = "; ".join(f"need {need} {p}, have {have}" for p, (need, have) in err.shortages.items())
        raise ToolError(f"Not enough plants: {missing}.") from None
    effect = json.dumps(potion.effect.to_dict())
    return ToolResult(f"Brewed {json.dumps(potion.recipe)} → {effect} (potion #{potion.id})", ends_turn=True)
