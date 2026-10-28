"""The complete world state: garden, inventory, knowledge base, goals and turn clock."""

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from environment.brewer import PLANTS, RecipeError, brew, validate_recipe
from environment.garden import Garden, GatherResult, PlantResult, sample_growth_times
from environment.goals import Allergy, Goal, GoalKind, GoalResult, goal_intensity, score_goal, validate_allergy
from environment.inventory import Inventory, Potion
from environment.knowledge_base import LABELS, GardenLogResult, KnowledgeBase, LogError, Outcome, effect_label
from environment.lore import LORE, pairs_among
from environment.view import GardenView, garden_view


class InfeasibleBrew(Exception):
    """Not enough plants; costs no turn."""

    def __init__(self, shortages: dict[str, tuple[int, int]]) -> None:
        super().__init__(shortages)
        self.shortages = shortages


@dataclass(frozen=True)
class PotionLog:
    potion_id: int
    outcome: Outcome
    new: bool  # False: exact duplicate, already known
    new_lore: int = 0  # lore lines this log unlocked for the potion's plants


@dataclass(frozen=True)
class LogResult:
    garden: GardenLogResult | None
    potions: list[PotionLog]


@dataclass(frozen=True)
class TurnEnd:
    finished: GoalResult | None  # goal that ended this turn
    next_goal: Goal | None       # goal that starts next turn
    episode_over: bool


@dataclass
class World:
    garden: Garden
    inventory: Inventory
    kb: KnowledgeBase
    goals: list[Goal]
    allergy: Allergy | None
    turn_cap: int
    lore: bool = True  # logging potions unlocks herbal lore
    turn: int = 1
    goal_index: int = 0
    goal_start: int = 1
    results: list[GoalResult] = field(default_factory=list)
    _target_reached: bool = field(default=False, repr=False)
    _gathered_this_turn: set[str] = field(default_factory=set, repr=False)  # empty at every checkpoint

    @classmethod
    def create(
        cls,
        size: int,
        growth_range: tuple[int, int],
        goals: Sequence[Goal],
        allergy: Allergy | None,
        turn_cap: int,
        seed: int,
        kb_path: str = ":memory:",
        lore: bool = True,
    ) -> "World":
        if not goals:
            raise ValueError("An episode needs at least one goal.")
        validate_allergy(allergy, goals)
        growth = sample_growth_times(PLANTS, *growth_range, random.Random(seed))
        kb = KnowledgeBase(kb_path, catalogue=[(p, None) for p in PLANTS])
        return cls(Garden(size, growth), Inventory(), kb, list(goals), allergy, turn_cap, lore)

    def to_dict(self) -> dict:
        """Complete state, including the knowledge base contents."""
        return {
            "garden": self.garden.to_dict(),
            "inventory": self.inventory.to_dict(),
            "knowledge_base": self.kb.dump(),
            "goals": [g.to_dict() for g in self.goals],
            "allergy": sorted(self.allergy.plants) if self.allergy else None,
            "turn_cap": self.turn_cap,
            "lore": self.lore,
            "turn": self.turn,
            "goal_index": self.goal_index,
            "goal_start": self.goal_start,
            "results": [r.to_dict() for r in self.results],
            "target_reached": self._target_reached,
        }

    @classmethod
    def from_dict(cls, data: Mapping, kb_path: str = ":memory:") -> "World":
        """Rebuild a world; the knowledge base at kb_path is overwritten with the saved contents."""
        kb = KnowledgeBase(kb_path)
        kb.restore(data["knowledge_base"])
        return cls(
            garden=Garden.from_dict(data["garden"]),
            inventory=Inventory.from_dict(data["inventory"]),
            kb=kb,
            goals=[Goal.from_dict(g) for g in data["goals"]],
            allergy=Allergy(frozenset(data["allergy"])) if data["allergy"] else None,
            turn_cap=data["turn_cap"],
            lore=data.get("lore", False),
            turn=data["turn"],
            goal_index=data["goal_index"],
            goal_start=data["goal_start"],
            results=[GoalResult.from_dict(r) for r in data["results"]],
            _target_reached=data["target_reached"],
        )

    @property
    def current_goal(self) -> Goal | None:
        return self.goals[self.goal_index] if self.goal_index < len(self.goals) else None

    @property
    def episode_over(self) -> bool:
        return self.current_goal is None or self.turn > self.turn_cap

    # --- actions (each costs the turn if it returns) ------------------------

    def plant(self, assignments: Mapping[int, str]) -> PlantResult:
        return self.garden.plant(assignments, self.turn)

    def gather(self) -> GatherResult:
        result = self.garden.gather(self.turn)
        self._gathered_this_turn.update(result.counts)
        self.kb.clear_plantings(result.plots)
        self.inventory.add_plants(result.counts)
        return result

    def brew(self, recipe: Mapping[str, int]) -> Potion:
        """Raises RecipeError or InfeasibleBrew (no turn cost) before changing anything."""
        return self.brew_all([recipe])[0]

    def brew_all(self, recipes: Sequence[Mapping[str, int]]) -> list[Potion]:
        """Brew several potions in one action, all or nothing: every recipe must be valid and the
        inventory must cover all of them together. Raises RecipeError or InfeasibleBrew before
        changing anything."""
        if not recipes:
            raise RecipeError("Give at least one recipe.")
        for i, recipe in enumerate(recipes, start=1):
            try:
                validate_recipe(recipe)
            except RecipeError as err:
                raise RecipeError(f"Recipe {i}: {err}" if len(recipes) > 1 else str(err)) from None
        total: Counter[str] = Counter()
        for recipe in recipes:
            total.update(recipe)
        if shortages := self.inventory.shortages(total):
            raise InfeasibleBrew(shortages)
        return [self._brew_one(recipe) for recipe in recipes]

    def _brew_one(self, recipe: Mapping[str, int]) -> Potion:
        self.inventory.consume(recipe)
        potion = self.inventory.add_potion(recipe, brew(recipe), self.turn)
        goal = self.current_goal
        valid = self.allergy is None or not self.allergy.violated_by(recipe)
        if goal and goal.kind is GoalKind.TARGET and valid and goal_intensity(goal, potion) >= goal.target:
            self._target_reached = True
        return potion

    def log(self, garden: bool, potions: Mapping[int, Mapping[str, str]]) -> LogResult:
        """Raises LogError (no turn cost) before writing anything if a potion entry is invalid."""
        entries = []
        for pid, labels in potions.items():
            if not 1 <= pid <= len(self.inventory.potions):
                raise LogError(f"Unknown potion #{pid}.")
            potion = self.inventory.potions[pid - 1]
            if extra := sorted(set(labels) - potion.recipe.keys()):
                raise LogError(f"Potion #{pid} does not contain {extra[0]}.")
            if bad := sorted(set(labels.values()) - set(LABELS)):
                raise LogError(f'Invalid label "{bad[0]}" (allowed: {", ".join(LABELS)}).')
            full = {p: labels.get(p, "present") for p in sorted(potion.recipe)}
            entries.append((potion, full))
        garden_result = None
        if garden:
            state = self.garden.state(self.turn)
            garden_result = self.kb.log_garden(state, self.garden.growth_times, also_ready=self._gathered_this_turn)
        logs = []
        for potion, labels in entries:
            effect = effect_label(potion.effect)
            new = self.kb.log_outcome(labels, effect, potion.id, self.turn)
            potion.logged = True
            unlocked = 0
            if self.lore:
                pairs = pairs_among(potion.recipe)
                unlocked = len(self.kb.unlock_lore({p: LORE[p] for p in pairs}, self.turn))
            logs.append(PotionLog(potion.id, Outcome(labels, effect), new, unlocked))
        return LogResult(garden_result, logs)

    def skip(self) -> None:
        pass

    # --- free lookups --------------------------------------------------------

    def view(self) -> GardenView:
        return garden_view(self.garden.state(self.turn), self.kb)

    # --- turn clock ------------------------------------------------------------

    def end_turn(self) -> TurnEnd:
        """Check the goal, then advance the clock."""
        goal = self.current_goal
        finished = None
        if goal is not None:
            deadline = goal.kind is GoalKind.TIME and self.turn >= self.goal_start + goal.turns - 1
            if self._target_reached or deadline or self.turn >= self.turn_cap:
                finished = score_goal(goal, self.inventory.potions, self.allergy, self.goal_start, self.turn)
                self.results.append(finished)
                self.goal_index += 1
                self.goal_start = self.turn + 1
                self._target_reached = False
        over = self.current_goal is None or self.turn >= self.turn_cap
        self.turn += 1
        self._gathered_this_turn.clear()
        next_goal = self.current_goal if finished and not over else None
        return TurnEnd(finished, next_goal, over)
