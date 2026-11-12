"""The notebook's automatic records and their lookups. Potion records come from the inventory (every brew
and mix), growth records from the garden (every finished planting); the environment writes both, so they
are always correct. Agent-written records (claims, beliefs, requirements) come later."""

import json
from collections.abc import Iterable, Sequence

from environment.garden import GrowthRecord
from environment.inventory import Potion

MAX_ROWS = 30


def potion_matches(
    potion: Potion,
    effect: str | None = None,       # "+S", "-S" or "none" (no primary effect)
    intensity: int | None = None,    # exact intensity of that effect
    secondary: str | None = None,    # a secondary label
    contains: Iterable[str] = (),    # every one of these plants is in the recipe
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
    return set(contains) <= potion.recipe.keys()


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
