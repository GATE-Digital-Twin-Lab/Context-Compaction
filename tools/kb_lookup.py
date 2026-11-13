"""Free tool: notebook lookups. Every field but "type" is optional; the more fields, the narrower the
answer (at most 30 rows, with the total count). Replaced records are hidden unless "replaced": true.
  {"tool": "kb_lookup", "type": "potion", "effect": "+S", "intensity": 25, "secondary": "sweet",
   "pattern": {"sage": "any", "mint": 2}}   (a pattern, or a list of patterns of which any may match)
  {"tool": "kb_lookup", "type": "growth", "plant": "sage", "soil": "yellow"}
  {"tool": "kb_lookup", "type": "claim", "source": "S7", "name": "pond plant", "plant": "nettle", "trust": "high"}
  {"tool": "kb_lookup", "type": "belief", "status": "false", "plant": "sage"}
  {"tool": "kb_lookup", "type": "requirement", "open": true}"""

import json
import re

from environment.brewer import MODIFIERS, PLANTS
from environment.notebook import find_growth, find_potions, growth_row, listing, parse_patterns, potion_row
from environment.records import TRUST, Record
from environment.validator import check
from environment.soils import SOILS
from environment.world import World
from tools.base import ToolError, ToolResult, require_int

FIELDS = {
    "potion": {"effect", "intensity", "secondary", "pattern"},
    "growth": {"plant", "soil"},
    "claim": {"source", "name", "plant", "trust", "replaced"},
    "belief": {"status", "plant", "replaced"},
    "requirement": {"open", "replaced"},
}


def run(world: World, args: dict) -> ToolResult:
    kind = args.get("type")
    if kind not in FIELDS:
        raise ToolError('"type" must be one of: ' + ", ".join(FIELDS) + ".")
    if extra := sorted(set(args) - FIELDS[kind] - {"tool", "type"}):
        raise ToolError(f'Unknown field "{extra[0]}" for {kind} records (allowed: {", ".join(sorted(FIELDS[kind]))}).')
    if kind == "growth":
        plant, soil = _choice(args, "plant", PLANTS), _choice(args, "soil", SOILS)
        rows = [growth_row(r) for r in find_growth(world.growth_records().values(), plant, soil)]
        return ToolResult(listing("growth", rows))
    if kind in ("claim", "belief", "requirement"):
        return ToolResult(_agent_records(world, kind, args))

    effect = args.get("effect")
    if effect is not None and not (isinstance(effect, str) and (effect == "none" or re.fullmatch(r"[+-][ISVDW]", effect))):
        raise ToolError('"effect" must be like "+S" or "-I", or "none".')
    intensity = None
    if "intensity" in args:
        if effect in (None, "none"):
            raise ToolError('"intensity" needs an "effect" such as "+S".')
        intensity = require_int(args["intensity"], '"intensity"')
    secondary = _choice(args, "secondary", MODIFIERS)
    patterns = ()
    if "pattern" in args:
        try:
            patterns = parse_patterns(args["pattern"])
        except ValueError as err:
            raise ToolError(str(err)) from None
    potions = find_potions(world.inventory.potions, effect=effect, intensity=intensity, secondary=secondary,
                           patterns=patterns)
    return ToolResult(listing("potion", [potion_row(p) for p in potions]))


def _choice(args: dict, key: str, allowed) -> str | None:
    value = args.get(key)
    if value is not None and value not in allowed:
        raise ToolError(f'Unknown {key} {value!r} (allowed: {", ".join(allowed)}).')
    return value


def _flag(args: dict, key: str) -> bool:
    value = args.get(key, False)
    if not isinstance(value, bool):
        raise ToolError(f'"{key}" must be true or false.')
    return value


def _agent_records(world: World, kind: str, args: dict) -> str:
    show_replaced = _flag(args, "replaced")
    plant = _choice(args, "plant", PLANTS)
    rows = []
    for r in world.records.records:
        if r.type != kind or (r.replaced_by and not show_replaced):
            continue
        if plant is not None and plant not in r.plants():
            continue
        f = r.fields
        if kind == "claim":
            if "source" in args and f["source"] != args["source"]:
                continue
            if "name" in args and f["says"].get("name") != args["name"]:
                continue
            if _choice(args, "trust", TRUST) not in (None, f["trust"]):
                continue
            rows.append(_row(r, f"source {f['source']}, trust {f['trust']}", f'"{f["quote"]}" → {json.dumps(f["says"])}'))
        elif kind == "belief":
            answer = check(f["statement"], world.inventory.potions, world.garden.history)
            if _choice(args, "status", ("true", "false", "unknown")) not in (None, answer["status"]):
                continue
            verdict = f'{answer["status"]}, tested {answer["tested"]}'
            if answer.get("against"):
                verdict += f", against {json.dumps(answer['against'])}"
            rows.append(_row(r, verdict, json.dumps(f["statement"])))
        else:
            if _flag(args, "open") and not r.is_open:
                continue
            body = f'"{f["phrase"]}" → {json.dumps(f.get("means", {}))}'
            if f.get("open"):
                body += f"; open: {f['open']}"
            rows.append(_row(r, None, body))
    return listing(kind, rows)


def _row(r: Record, extra: str | None, body: str) -> str:
    """E.g. 'b2 (turn 14, true, tested 4): {...}; from c3; why: ...'."""
    details = [f"turn {r.turn}"] + ([extra] if extra else [])
    if "replaces" in r.fields:
        details.append(f"replaces {r.fields['replaces']}")
    if r.replaced_by:
        details.append(f"replaced by {r.replaced_by}")
    text = f"{r.id} ({', '.join(details)}): {body}"
    if r.fields.get("from"):
        text += "; from " + ", ".join(r.fields["from"])
    if r.fields.get("why"):
        text += f"; why: {r.fields['why']}"
    return text
