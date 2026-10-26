"""Hidden brewing rules. Never import from agent-facing code."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

PLANTS = tuple(f"p{i}" for i in range(1, 9))
MIN_PLANTS, MAX_PLANTS = 3, 4
LEVELS = (2, 5, 10, 20)

STAT_SETS: dict[str, tuple[str, ...]] = {
    "I": ("p2", "p4", "p6"),
    "S": ("p1", "p5", "p8"),
    "V": ("p1", "p3", "p7"),
    "D": ("p3", "p4", "p8"),
    "W": ("p2", "p5", "p6", "p7"),
}


class RecipeError(ValueError):
    """Recipe is malformed (unknown plant, bad count, wrong number of plants)."""


@dataclass(frozen=True)
class Effect:
    """Brew outcome: stat -> intensity (%) for positive and negative effects."""

    positive: dict[str, int] = field(default_factory=dict)
    negative: dict[str, int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.positive and not self.negative

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"positive": dict(self.positive), "negative": dict(self.negative)}


def intensity(score: int) -> int:
    """Map a driver score to an intensity level; score <= 0 gives no effect."""
    if score <= 0:
        return 0
    return LEVELS[min(score, len(LEVELS)) - 1]


# Each rule returns (positive score, negative score); None means the condition fails.
Rule = Callable[[Mapping[str, int]], tuple[int | None, int | None]]

_RULES: dict[str, Rule] = {
    "I": lambda n: (
        n["p2"] if n["p4"] % 2 == 1 else None,
        n["p2"] if n["p4"] % 3 == 0 else None,
    ),
    "S": lambda n: (
        n["p5"] if n["p8"] % 3 == 2 and n["p1"] == 2 else None,
        n["p5"] if n["p8"] % 2 == 1 else None,
    ),
    "V": lambda n: (
        n["p7"] if n["p7"] % 5 != 0 and n["p3"] % 2 == 0 else None,
        n["p7"] if n["p1"] == 2 else None,
    ),
    "D": lambda n: (
        n["p8"] - n["p4"] + 1 if n["p4"] % 2 == 1 else None,
        n["p8"] + n["p4"] - 2 if n["p4"] % 2 == 0 else None,
    ),
    "W": lambda n: (
        n["p6"] if n["p2"] == 2 and n["p7"] % 2 == 1 else None,
        n["p6"] if n["p7"] % 2 == 1 and n["p5"] % 2 == 0 else None,
    ),
}


def validate_recipe(recipe: Mapping[str, int]) -> None:
    """Raise RecipeError if the recipe breaks the brewing rules."""
    for plant, count in recipe.items():
        if plant not in PLANTS:
            raise RecipeError(f"Unknown plant {plant}.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise RecipeError(f"Invalid count for {plant}: {count!r}.")
    if not MIN_PLANTS <= len(recipe) <= MAX_PLANTS:
        raise RecipeError(f"A recipe needs {MIN_PLANTS}–{MAX_PLANTS} distinct plants.")


def brew(recipe: Mapping[str, int]) -> Effect:
    """Return the effect of a valid recipe (inventory is not checked here)."""
    validate_recipe(recipe)
    positive: dict[str, int] = {}
    negative: dict[str, int] = {}
    for stat, plants in STAT_SETS.items():
        if not all(p in recipe for p in plants):
            continue
        pos_score, neg_score = _RULES[stat](recipe)
        pos = intensity(pos_score) if pos_score is not None else 0
        neg = intensity(neg_score) if neg_score is not None else 0
        if pos and neg:
            continue  # both hold: they cancel, whatever the magnitudes
        if pos:
            positive[stat] = pos
        elif neg:
            negative[stat] = neg
    return Effect(positive, negative)
