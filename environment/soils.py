"""Hidden soil table (demo_spec.md): growth time and survival chance per (plant, soil).
Never import from agent-facing code."""

import random

SOILS = ("black", "brown", "yellow")

# plant -> soil -> (growth time in turns, survival chance in %). 0% never survives: the death is
# reported after the growth time, and the dead plant occupies its plot until gathered.
# Sampled with seed 17, hand-edited, frozen.
SOIL_TABLE: dict[str, dict[str, tuple[int, int]]] = {
    "mint":       {"black": (6, 100), "brown": (2, 100), "yellow": (5, 100)},
    "elderberry": {"black": (5, 100), "brown": (2, 0),   "yellow": (3, 0)},
    "nettle":     {"black": (4, 0),   "brown": (6, 0),   "yellow": (5, 100)},
    "sage":       {"black": (4, 0),   "brown": (5, 100), "yellow": (2, 100)},
    "chamomile":  {"black": (4, 100), "brown": (5, 100), "yellow": (3, 100)},
    "dill":       {"black": (3, 100), "brown": (2, 75),  "yellow": (3, 0)},
    "basil":      {"black": (6, 0),   "brown": (6, 100), "yellow": (3, 100)},
    "rosemary":   {"black": (4, 100), "brown": (4, 100), "yellow": (6, 100)},
}


def growth_time(plant: str, soil: str) -> int:
    return SOIL_TABLE[plant][soil][0]


def survival(plant: str, soil: str) -> int:
    return SOIL_TABLE[plant][soil][1]


def survives(plant: str, soil: str, seed: int, plot: int, turn: int) -> bool:
    """Whether one planting survives. Chance pairs roll from (env seed, plot, planting turn), so the
    outcome is reproducible and needs no random state in checkpoints."""
    chance = survival(plant, soil)
    if chance >= 100 or chance <= 0:
        return chance >= 100
    return random.Random(f"{seed}:{plot}:{turn}").random() * 100 < chance
