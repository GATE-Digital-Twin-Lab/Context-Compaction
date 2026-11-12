"""Mix action: {"action": "mix", "mixes": [[4, 9], [5, 6, 7]]}. Each mix combines held potions into one
potion brewed from their summed recipe; the inputs are used up. All or nothing; costs one turn."""

import json

from environment.world import MixError, World
from tools.base import ToolError, ToolResult, require_int


def run(world: World, args: dict) -> ToolResult:
    mixes = args.get("mixes")
    if not isinstance(mixes, list) or not mixes or not all(isinstance(m, list) for m in mixes):
        raise ToolError('"mixes" must be a non-empty list of potion-id lists, e.g. [[4, 9]].')
    ids = [[require_int(pid, "A potion id") for pid in mix] for mix in mixes]
    try:
        potions = world.mix_all(ids)
    except MixError as err:
        raise ToolError(f"{err} Nothing was mixed.") from None
    lines = [
        f"Mixed {' + '.join(f'#{i}' for i in p.origin)}: {json.dumps(p.recipe)} → "
        f"{json.dumps(p.effect.to_dict())} (potion #{p.id})"
        for p in potions
    ]
    return ToolResult("\n".join(lines), ends_turn=True)
