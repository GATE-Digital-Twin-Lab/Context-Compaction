"""Hidden brewing rules. Never import from agent-facing code."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

PLANTS = ("mint", "elderberry", "nettle", "sage", "chamomile", "dill", "basil", "rosemary")
MIN_PLANTS, MAX_PLANTS = 2, 4  # per brew; a mix (summed recipe) has no plant limit
LEVELS = (2, 5, 10, 20)

STAT_SETS: dict[str, tuple[str, ...]] = {
    "I": ("elderberry", "sage", "dill"),
    "S": ("mint", "chamomile", "rosemary"),
    "V": ("mint", "nettle", "basil"),
    "D": ("nettle", "sage", "rosemary"),
    "W": ("elderberry", "chamomile", "dill", "basil"),
}

# Secondary effects: label -> modifier (%), and the pairs that give each label.
# No pair lies inside a stat set; a label's two pairs share no plant (see demo_spec.md).
MODIFIERS: dict[str, int] = {
    "fragrant": 25,
    "warming": 50,
    "sweet": 100,
    "bitter": -25,
    "murky": -50,
    "toxic": -100,
}
SECONDARY_PAIRS: dict[frozenset[str], str] = {
    frozenset(("mint", "sage")): "fragrant",
    frozenset(("basil", "rosemary")): "fragrant",
    frozenset(("chamomile", "nettle")): "warming",
    frozenset(("basil", "sage")): "warming",
    frozenset(("dill", "mint")): "sweet",
    frozenset(("chamomile", "sage")): "sweet",
    frozenset(("elderberry", "mint")): "bitter",
    frozenset(("dill", "rosemary")): "bitter",
    frozenset(("elderberry", "rosemary")): "murky",
    frozenset(("dill", "nettle")): "murky",
    frozenset(("elderberry", "nettle")): "toxic",
}
_LABEL_ORDER = {label: i for i, label in enumerate(MODIFIERS)}


def secondary_labels(plants: Iterable[str]) -> tuple[str, ...]:
    """One label per listed pair present, in MODIFIERS order (a label shows twice if both its pairs are)."""
    present = set(plants)
    found = [label for pair, label in SECONDARY_PAIRS.items() if pair <= present]
    return tuple(sorted(found, key=_LABEL_ORDER.__getitem__))


def net_modifier(labels: Iterable[str]) -> int:
    """Sum of the modifiers (%); 0 if positive and negative modifiers are both present (they cancel)."""
    mods = [MODIFIERS[label] for label in labels]
    if any(m > 0 for m in mods) and any(m < 0 for m in mods):
        return 0
    return sum(mods)


def apply_modifier(base: int, modifier: int) -> int:
    """base × (1 + modifier/100), clamped at 0, rounded half away from zero (2.5 -> 3)."""
    scaled = base * (100 + modifier)  # hundredths of a percent; base >= 0
    return (scaled + 50) // 100 if scaled > 0 else 0


class RecipeError(ValueError):
    """Recipe is malformed (unknown plant, bad count, wrong number of plants)."""


@dataclass(frozen=True)
class Effect:
    """Brew outcome: stat -> final intensity (%) for positive and negative effects, and the
    secondary labels (one per pair present)."""

    positive: dict[str, int] = field(default_factory=dict)
    negative: dict[str, int] = field(default_factory=dict)
    secondary: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """No primary effect (secondary labels may still be present)."""
        return not self.positive and not self.negative

    @property
    def drinkable(self) -> bool:
        """False if toxic or the net modifier is <= -100% (a toxic cancelled by a positive is drinkable)."""
        return net_modifier(self.secondary) > -100

    def to_dict(self) -> dict:
        return {"positive": dict(self.positive), "negative": dict(self.negative), "secondary": list(self.secondary)}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Effect":
        return cls(dict(data["positive"]), dict(data["negative"]), tuple(data.get("secondary", ())))


def intensity(score: int) -> int:
    """Map a driver score to an intensity level; score <= 0 gives no effect."""
    if score <= 0:
        return 0
    return LEVELS[min(score, len(LEVELS)) - 1]


# Each rule returns (positive score, negative score); None means the condition fails.
Rule = Callable[[Mapping[str, int]], tuple[int | None, int | None]]

_RULES: dict[str, Rule] = {
    "I": lambda n: (
        n["elderberry"] if n["sage"] % 2 == 1 else None,
        n["elderberry"] if n["sage"] % 3 == 0 else None,
    ),
    "S": lambda n: (
        n["chamomile"] if n["rosemary"] % 3 == 2 and n["mint"] == 2 else None,
        n["chamomile"] if n["rosemary"] % 2 == 1 else None,
    ),
    "V": lambda n: (
        n["basil"] if n["basil"] % 5 != 0 and n["nettle"] % 2 == 0 else None,
        n["basil"] if n["mint"] == 2 else None,
    ),
    "D": lambda n: (
        n["rosemary"] - n["sage"] + 1 if n["sage"] % 2 == 1 else None,
        n["rosemary"] + n["sage"] - 2 if n["sage"] % 2 == 0 else None,
    ),
    "W": lambda n: (
        n["dill"] if n["elderberry"] == 2 and n["basil"] % 2 == 1 else None,
        n["dill"] if n["basil"] % 2 == 1 and n["chamomile"] % 2 == 0 else None,
    ),
}


def validate_counts(recipe: Mapping[str, int]) -> None:
    """Raise RecipeError for an unknown plant or a count that is not a whole number >= 1."""
    for plant, count in recipe.items():
        if plant not in PLANTS:
            raise RecipeError(f"Unknown plant {plant}.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise RecipeError(f"Invalid count for {plant}: {count!r}.")


def validate_recipe(recipe: Mapping[str, int]) -> None:
    """Raise RecipeError if the recipe breaks the brewing rules."""
    validate_counts(recipe)
    if not MIN_PLANTS <= len(recipe) <= MAX_PLANTS:
        raise RecipeError(f"A recipe needs {MIN_PLANTS}–{MAX_PLANTS} distinct plants.")


def brew(recipe: Mapping[str, int]) -> Effect:
    """Return the effect of a valid recipe (inventory is not checked here)."""
    validate_recipe(recipe)
    return effect_of(recipe)


def effect_of(recipe: Mapping[str, int]) -> Effect:
    """Effect of any recipe with valid counts and no plant limit: a brew, or the summed recipe of a mix.
    Every active stat gets its base level, scaled by the net secondary modifier."""
    validate_counts(recipe)
    labels = secondary_labels(recipe)
    modifier = net_modifier(labels)
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
        if pos and (value := apply_modifier(pos, modifier)):
            positive[stat] = value
        elif neg and (value := apply_modifier(neg, modifier)):
            negative[stat] = value
    return Effect(positive, negative, labels)
