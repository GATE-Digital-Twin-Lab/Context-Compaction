"""The notebook's automatic records and their lookups. Potion records come from the inventory (every brew
and mix), growth records from the garden (every finished planting); the environment writes both, so they
are always correct. Agent-written records (claims, beliefs, requirements) come later."""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from environment.brewer import PLANTS
from environment.garden import GrowthRecord
from environment.inventory import Potion

MAX_ROWS = 30
CONDITIONS = ("any", "odd", "even", "absent")


@dataclass(frozen=True)
class Pattern:
    """Conditions on a recipe's plants: an exact count, "any" (present), "odd", "even" or "absent".
    only: the recipe has no plants besides the (non-absent) ones named."""

    plants: tuple[tuple[str, int | str], ...]
    only: bool = False

    def matches(self, recipe: Mapping[str, int]) -> bool:
        for plant, cond in self.plants:
            n = recipe.get(plant, 0)
            if cond == "absent":
                if n:
                    return False
            elif n == 0:
                return False
            elif (cond == "odd" and n % 2 == 0) or (cond == "even" and n % 2 == 1):
                return False
            elif isinstance(cond, int) and n != cond:
                return False
        if self.only:
            named = {p for p, cond in self.plants if cond != "absent"}
            return recipe.keys() <= named
        return True


def parse_pattern(value) -> Pattern:
    """{"mint": 2, "chamomile": "any", "sage": "odd", "only": true} → Pattern. Raises ValueError."""
    if not isinstance(value, dict) or not value:
        raise ValueError('A pattern is an object such as {"mint": 2, "sage": "odd", "chamomile": "any"}.')
    only = value.get("only", False)
    if not isinstance(only, bool):
        raise ValueError('"only" must be true or false.')
    plants = []
    for plant, cond in value.items():
        if plant == "only":
            continue
        if plant not in PLANTS:
            raise ValueError(f"Unknown plant {plant}.")
        if isinstance(cond, bool) or not (cond in CONDITIONS or (isinstance(cond, int) and cond >= 1)):
            raise ValueError(f'The condition for {plant} must be a count >= 1 or one of: {", ".join(CONDITIONS)}.')
        plants.append((plant, cond))
    return Pattern(tuple(plants), only)


def parse_patterns(value) -> tuple[Pattern, ...]:
    """One pattern, or a list of patterns of which any may match."""
    items = value if isinstance(value, list) else [value]
    if not items:
        raise ValueError("Give at least one pattern.")
    return tuple(parse_pattern(v) for v in items)


def matches_any(patterns: Iterable[Pattern], recipe: Mapping[str, int]) -> bool:
    return any(p.matches(recipe) for p in patterns)


def potion_matches(
    potion: Potion,
    effect: str | None = None,       # "+S", "-S" or "none" (no primary effect)
    intensity: int | None = None,    # exact intensity of that effect
    secondary: str | None = None,    # a secondary label
    patterns: Sequence[Pattern] = (),  # the recipe matches one of these patterns
) -> bool:
    e = potion.effect
    if effect == "none":
        if not e.is_empty:
            return False
    elif effect is not None:
        side = e.positive if effect[0] == "+" else e.negative
        if effect[1:] not in side or (intensity is not None and side[effect[1:]] != intensity):
            return False
    if secondary is not None and secondary not in e.secondary:
        return False
    return not patterns or matches_any(patterns, potion.recipe)


def find_potions(potions: Sequence[Potion], **filters) -> list[Potion]:
    """Matching potion records, oldest first."""
    return [p for p in potions if potion_matches(p, **filters)]


def find_growth(records: Iterable[GrowthRecord], plant: str | None = None, soil: str | None = None) -> list[GrowthRecord]:
    return [r for r in records if (plant is None or r.plant == plant) and (soil is None or r.soil == soil)]


def potion_row(p: Potion) -> str:
    """E.g. '#4 (turn 12, mix of #2 + #3, used): {"mint": 2, ...} → {"positive": {"S": 25}, ...}'."""
    details = [f"turn {p.turn}"]
    if p.origin:
        details.append("mix of " + " + ".join(f"#{i}" for i in p.origin))
    if p.used:
        details.append("used")
    return f"#{p.id} ({', '.join(details)}): {json.dumps(p.recipe)} → {json.dumps(p.effect.to_dict())}"


def growth_row(r: GrowthRecord) -> str:
    """E.g. 'sage in yellow: 2 turns (planted 3, grew 3, died 0)'."""
    unit = "turn" if r.turns == 1 else "turns"
    return f"{r.plant} in {r.soil}: {r.turns} {unit} (planted {r.planted}, grew {r.grew}, died {r.died})"


def listing(kind: str, rows: Sequence[str]) -> str:
    """At most MAX_ROWS rows, oldest first, with the total count."""
    if not rows:
        return f"No {kind} records match."
    head = f"{len(rows)} {kind} record{'s' if len(rows) != 1 else ''}"
    if len(rows) > MAX_ROWS:
        head += f", showing the first {MAX_ROWS}: give more fields to narrow the lookup"
    return "\n".join([head + ":"] + [f"- {row}" for row in rows[:MAX_ROWS]])
