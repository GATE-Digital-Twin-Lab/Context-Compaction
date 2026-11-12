"""Free tool: notebook lookups over the automatic records. Every field but "type" is optional; the more
fields, the narrower the answer (at most 30 rows, with the total count).
  {"tool": "kb_lookup", "type": "potion", "effect": "+S", "intensity": 25, "secondary": "sweet", "contains": ["sage", "mint"]}
  {"tool": "kb_lookup", "type": "growth", "plant": "sage", "soil": "yellow"}"""

import re

from environment.brewer import MODIFIERS, PLANTS
from environment.notebook import find_growth, find_potions, growth_row, listing, potion_row
from environment.soils import SOILS
from environment.world import World
from tools.base import ToolError, ToolResult, require_int

FIELDS = {"potion": {"effect", "intensity", "secondary", "contains"}, "growth": {"plant", "soil"}}


def run(world: World, args: dict) -> ToolResult:
    kind = args.get("type")
    if kind not in FIELDS:
        raise ToolError('"type" must be "potion" or "growth".')
    if extra := sorted(set(args) - FIELDS[kind] - {"tool", "type"}):
        raise ToolError(f'Unknown field "{extra[0]}" for {kind} records (allowed: {", ".join(sorted(FIELDS[kind]))}).')
    if kind == "growth":
        plant, soil = _choice(args, "plant", PLANTS), _choice(args, "soil", SOILS)
        rows = [growth_row(r) for r in find_growth(world.growth_records().values(), plant, soil)]
        return ToolResult(listing("growth", rows))

    effect = args.get("effect")
    if effect is not None and not (isinstance(effect, str) and (effect == "none" or re.fullmatch(r"[+-][ISVDW]", effect))):
        raise ToolError('"effect" must be like "+S" or "-I", or "none".')
    intensity = None
    if "intensity" in args:
        if effect in (None, "none"):
            raise ToolError('"intensity" needs an "effect" such as "+S".')
        intensity = require_int(args["intensity"], '"intensity"')
    secondary = _choice(args, "secondary", MODIFIERS)
    contains = args.get("contains", [])
    if not isinstance(contains, list) or not all(isinstance(p, str) for p in contains):
        raise ToolError('"contains" must be a list of plant names.')
    if unknown := [p for p in contains if p not in PLANTS]:
        raise ToolError(f"Unknown plant {unknown[0]}.")
    potions = find_potions(world.inventory.potions, effect=effect, intensity=intensity, secondary=secondary,
                           contains=contains)
    return ToolResult(listing("potion", [potion_row(p) for p in potions]))


def _choice(args: dict, key: str, allowed) -> str | None:
    value = args.get(key)
    if value is not None and value not in allowed:
        raise ToolError(f'Unknown {key} {value!r} (allowed: {", ".join(allowed)}).')
    return value
