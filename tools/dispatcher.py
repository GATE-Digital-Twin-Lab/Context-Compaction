"""Routes one agent call to its tool and enforces the failure limit per turn."""

import json
from collections.abc import Callable

from environment.world import World
from tools import brew, gather, inventory, kb_lookup, log, plant, skip
from tools.base import ToolError, ToolResult

ACTIONS: dict[str, Callable[[World, dict], ToolResult]] = {
    "plant": plant.run,
    "gather": gather.run,
    "log": log.run,
    "brew": brew.run,
    "skip": skip.run,
}
FREE_TOOLS: dict[str, Callable[[World, dict], ToolResult]] = {
    "kb_lookup": kb_lookup.run,
    "inventory": inventory.run,
}


class Dispatcher:
    """One call at a time; the failure counter resets when the world's turn changes."""

    def __init__(self, world: World, max_failures: int = 3) -> None:
        self.world = world
        self.max_failures = max_failures
        self._failures = 0
        self._turn = world.turn

    def handle(self, call: str | dict) -> ToolResult:
        if self.world.turn != self._turn:
            self._failures, self._turn = 0, self.world.turn
        try:
            return self._route(call)
        except ToolError as err:
            self._failures += 1
            if self._failures >= self.max_failures:
                self.world.skip()
                return ToolResult(
                    f"{err} {self.max_failures} failed attempts: the turn is skipped.",
                    ends_turn=True,
                    error=True,
                )
            return ToolResult(str(err), error=True)

    def _route(self, call: str | dict) -> ToolResult:
        if isinstance(call, str):
            try:
                call = json.loads(call)
            except json.JSONDecodeError:
                raise ToolError("Malformed JSON.") from None
        if not isinstance(call, dict):
            raise ToolError("A call must be a JSON object.")
        if ("action" in call) == ("tool" in call):
            raise ToolError('A call needs exactly one of "action" or "tool".')
        if "action" in call:
            name, table, kind = call["action"], ACTIONS, "action"
        else:
            name, table, kind = call["tool"], FREE_TOOLS, "tool"
        if name not in table:
            raise ToolError(f"Unknown {kind} {name!r} (allowed: {', '.join(table)}).")
        return table[name](self.world, call)
