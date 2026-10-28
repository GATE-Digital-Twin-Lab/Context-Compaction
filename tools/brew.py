"""Brew action: {"action": "brew", "recipes": [{"mint": 2, "chamomile": 4, "rosemary": 2}, ...]}
(or "recipe": {...} for a single potion). All or nothing; costs one turn however many potions."""

import json

from environment.brewer import RecipeError
from environment.world import InfeasibleBrew, World
from tools.base import ToolError, ToolResult, require_dict


def run(world: World, args: dict) -> ToolResult:
    if ("recipe" in args) == ("recipes" in args):
        raise ToolError('Give either "recipe" (one potion) or "recipes" (a list of potions).')
    if "recipe" in args:
        recipes = [require_dict(args, "recipe")]
    else:
        recipes = args["recipes"]
        if not isinstance(recipes, list) or not recipes or not all(isinstance(r, dict) for r in recipes):
            raise ToolError('"recipes" must be a non-empty list of recipe objects.')
    try:
        potions = world.brew_all(recipes)
    except RecipeError as err:
        raise ToolError(str(err)) from None
    except InfeasibleBrew as err:
        missing = "; ".join(f"need {need} {p}, have {have}" for p, (need, have) in err.shortages.items())
        scope = "for these recipes together" if len(recipes) > 1 else ""
        raise ToolError(f"Not enough plants{' ' + scope if scope else ''}: {missing}. Nothing was brewed.") from None
    lines = [
        f"Brewed {json.dumps(p.recipe)} → {json.dumps(p.effect.to_dict())} (potion #{p.id})" for p in potions
    ]
    return ToolResult("\n".join(lines), ends_turn=True)
