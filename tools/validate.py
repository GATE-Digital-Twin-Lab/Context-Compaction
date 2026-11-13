"""Free tool: {"tool": "validate", "statements": [{...}, ...]}. Checks each statement against the notebook's
records and answers "true", "false" or "unknown" with the evidence (see environment/validator.py)."""

import json

from environment.validator import check
from environment.world import World
from tools.base import ToolError, ToolResult


def run(world: World, args: dict) -> ToolResult:
    statements = args.get("statements")
    if not isinstance(statements, list) or not statements:
        raise ToolError('"statements" must be a non-empty list of statements.')
    lines = []
    for i, statement in enumerate(statements, start=1):
        try:
            answer = check(statement, world.inventory.potions, world.garden.history)
        except ValueError as err:
            where = f"Statement {i}: " if len(statements) > 1 else ""
            raise ToolError(f"{where}{err} Nothing was checked.") from None
        lines.append(f"{i}. {json.dumps(answer)}")
    return ToolResult("\n".join(lines))
