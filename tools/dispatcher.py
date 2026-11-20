"""Routes one agent call to its tool; enforces the failure limit and the counted-call budget per turn."""

import json
from collections.abc import Callable

from environment.world import World
from tools import brew, deliver, gather, inventory, kb_lookup, mix, plant, read, record, search, skip, validate
from tools.base import ToolError, ToolResult

ACTIONS: dict[str, Callable[[World, dict], ToolResult]] = {
    "plant": plant.run,
    "brew": brew.run,
    "mix": mix.run,
    "deliver": deliver.run,
    "skip": skip.run,
}
FREE_TOOLS: dict[str, Callable[[World, dict], ToolResult]] = {
    "search": search.run,
    "read": read.run,
    "gather": gather.run,
    "kb_lookup": kb_lookup.run,
    "validate": validate.run,
    "record": record.run,
    "inventory": inventory.run,
}
COUNTED = ("search", "record", "validate")
BUDGET = 5                         # counted calls per turn (a batched call counts once)


class Dispatcher:
    """One call at a time; the failure counter and the budget reset when the world's turn changes."""

    def __init__(self, world: World, max_failures: int = 3, budget: int = BUDGET) -> None:
        self.world = world
        self.max_failures = max_failures
        self.budget = budget
        self._failures = 0
        self._counted = 0
        self._turn = world.turn

    def handle(self, call: str | dict) -> ToolResult:
        if self.world.turn != self._turn:
            self._failures, self._counted, self._turn = 0, 0, self.world.turn
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
                if "{" not in call:
                    raise ToolError("No JSON call found: end your reply with one JSON call.") from None
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
        if name not in COUNTED:
            return table[name](self.world, call)
        if self._counted >= self.budget:   # not a failure: it costs nothing and does not lead to a skip
            return ToolResult(
                f"The budget of {self.budget} search/record/validate calls is used up this turn. Only read, "
                "kb_lookup, inventory, gather or an action remain until the next turn.",
                error=True,
            )
        result = table[name](self.world, call)
        self._counted += 1
        left = self.budget - self._counted
        return ToolResult(f"{result.text}\n({left} of {self.budget} search/record/validate calls left this turn.)",
                          result.ends_turn, result.error)
