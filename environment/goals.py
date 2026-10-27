"""User goals, the allergy rule, and per-goal scoring."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from environment.brewer import PLANTS, STAT_SETS
from environment.inventory import Potion


STAT_NAMES = {"I": "intelligence", "S": "strength", "V": "vitality", "D": "dexterity", "W": "wisdom"}


class GoalKind(StrEnum):
    TIME = "time"      # best potion within a turn budget
    TARGET = "target"  # reach an intensity as fast as possible


@dataclass(frozen=True)
class Goal:
    kind: GoalKind
    stat: str
    turns: int | None = None   # TIME: turn budget
    target: int | None = None  # TARGET: minimum intensity (%)

    def __post_init__(self) -> None:
        if self.stat not in STAT_SETS:
            raise ValueError(f"Unknown stat {self.stat}.")
        if self.kind is GoalKind.TIME and not (self.turns and self.turns >= 1 and self.target is None):
            raise ValueError("A time goal needs turns >= 1 and no target.")
        if self.kind is GoalKind.TARGET and not (self.target and self.target > 0 and self.turns is None):
            raise ValueError("A target goal needs a target > 0 and no turn budget.")

    def to_dict(self) -> dict:
        return {"kind": str(self.kind), "stat": self.stat, "turns": self.turns, "target": self.target}

    def describe(self) -> str:
        """E.g. 'brew the best strength (S) potion you can in 30 turns'."""
        name = f"{STAT_NAMES[self.stat]} ({self.stat})"
        if self.kind is GoalKind.TIME:
            return f"brew the best {name} potion you can in {self.turns} turns"
        return f"brew a {name} potion of at least +{self.target}% as fast as you can"


@dataclass(frozen=True)
class Allergy:
    plants: frozenset[str]

    def __post_init__(self) -> None:
        if len(self.plants) != 2 or not self.plants <= set(PLANTS):
            raise ValueError(f"An allergy needs two known plants, got {sorted(self.plants)}.")

    def violated_by(self, recipe: Mapping[str, int]) -> bool:
        return self.plants <= recipe.keys()


def validate_allergy(allergy: Allergy | None, goals: Iterable[Goal]) -> None:
    """The allergy must never make a goal impossible."""
    if allergy is None:
        return
    for goal in goals:
        if allergy.plants <= set(STAT_SETS[goal.stat]):
            raise ValueError(f"Allergy {sorted(allergy.plants)} makes the {goal.stat} goal impossible.")


def goal_intensity(goal: Goal, potion: Potion) -> int:
    """Positive intensity of the goal's stat (0 if none)."""
    return potion.effect.positive.get(goal.stat, 0)


@dataclass(frozen=True)
class GoalResult:
    goal: Goal
    start_turn: int
    end_turn: int
    best_potion: int | None   # potion id
    best_intensity: int
    success: bool
    allergy_violations: int

    @property
    def turns_used(self) -> int:
        return self.end_turn - self.start_turn + 1


def score_goal(
    goal: Goal, potions: Iterable[Potion], allergy: Allergy | None, start: int, end: int
) -> GoalResult:
    """Score the potions brewed in [start, end]; allergic potions don't count."""
    best_id, best, violations = None, 0, 0
    for potion in potions:
        if not start <= potion.turn <= end:
            continue
        if allergy is not None and allergy.violated_by(potion.recipe):
            violations += 1
            continue
        if (value := goal_intensity(goal, potion)) > best:
            best_id, best = potion.id, value
    if goal.kind is GoalKind.TARGET:
        success = best >= goal.target
    else:
        success = best > 0
    return GoalResult(goal, start, end, best_id, best, success, violations)
