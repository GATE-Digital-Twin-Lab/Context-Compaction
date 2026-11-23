"""Free tool (counted): {"tool": "record", "records": [{"type": "claim", ...}, ...]}. Writes the agent's
claims, beliefs and requirements, all or nothing (see environment/records.py). Beliefs are checked at once."""

import json

from environment.records import RecordError
from environment.validator import check
from environment.world import World
from tools.base import ToolError, ToolResult


def run(world: World, args: dict) -> ToolResult:
    raw = args.get("records")
    if world.library is not None and isinstance(raw, list):
        for rec in raw:
            if isinstance(rec, dict) and rec.get("type") == "claim" and isinstance(rec.get("source"), str) \
                    and rec["source"] not in world.library.sources:
                raise ToolError(f"Unknown source {rec['source']}: a claim cites a text id such as S12. Nothing was recorded.")
    try:
        records = world.record(args.get("records"))
    except RecordError as err:
        raise ToolError(f"{err} Nothing was recorded.") from None
    lines = []
    for r in records:
        line = r.id + (f" (replaces {r.fields['replaces']})" if "replaces" in r.fields else "")
        if r.type == "belief":
            line += ": " + json.dumps(check(r.fields["statement"], world.inventory.potions, world.garden.history))
        lines.append(line)
    return ToolResult("Recorded:\n" + "\n".join(f"- {line}" for line in lines))
