"""The complete world state: garden, inventory, knowledge base, the request and the turn clock."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from environment.brewer import PLANTS, Effect, RecipeError, brew, effect_of, validate_recipe
from environment.garden import Garden, GatherResult, GrowthRecord, PlantResult
from environment.inventory import Inventory, Potion
from environment.knowledge_base import LABELS, KnowledgeBase, LogError, Outcome, effect_label
from environment.lore import LORE, pairs_among
from environment.requests import Request, RequestResult, judge
from environment.view import GardenView, garden_view


class InfeasibleBrew(Exception):
    """Not enough plants; costs no turn."""

    def __init__(self, shortages: dict[str, tuple[int, int]]) -> None:
        super().__init__(shortages)
        self.shortages = shortages


class MixError(ValueError):
    """Invalid mix (unknown, used-up or repeated potion); costs no turn."""


class DeliveryError(ValueError):
    """Invalid delivery (unknown or used-up potion); costs no turn."""


@dataclass(frozen=True)
class PotionLog:
    potion_id: int
    outcome: Outcome
    new: bool  # False: exact duplicate, already known
    new_lore: int = 0  # lore lines this log unlocked for the potion's plants


@dataclass
class World:
    garden: Garden
    inventory: Inventory
    kb: KnowledgeBase
    request: Request
    turn_cap: int
    lore: bool = True  # logging potions unlocks herbal lore
    turn: int = 1
    result: RequestResult | None = None  # set by the delivery, or when time runs out

    @classmethod
    def create(
        cls,
        size: int,
        request: Request,
        turn_cap: int,
        seed: int,
        kb_path: str = ":memory:",
        lore: bool = True,
    ) -> "World":
        if turn_cap < 1:
            raise ValueError("The turn cap must be >= 1.")
        kb = KnowledgeBase(kb_path, catalogue=PLANTS)
        return cls(Garden(size, seed), Inventory(), kb, request, turn_cap, lore)

    def to_dict(self) -> dict:
        """Complete state, including the knowledge base contents."""
        return {
            "garden": self.garden.to_dict(),
            "inventory": self.inventory.to_dict(),
            "knowledge_base": self.kb.dump(),
            "request": self.request.to_dict(),
            "turn_cap": self.turn_cap,
            "lore": self.lore,
            "turn": self.turn,
            "result": self.result.to_dict() if self.result else None,
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
            request=Request.from_dict(data["request"]),
            turn_cap=data["turn_cap"],
            lore=data["lore"],
            turn=data["turn"],
            result=RequestResult.from_dict(data["result"]) if data["result"] else None,
        )

    @property
    def last_turn(self) -> int:
        """The deadline's last turn, or the turn cap if that comes first (or there is no deadline)."""
        deadline = self.request.deadline_turn
        return self.turn_cap if deadline is None else min(deadline, self.turn_cap)

    @property
    def episode_over(self) -> bool:
        return self.result is not None

    # --- actions (each costs the turn if it returns) ------------------------

    def plant(self, assignments: Mapping[int, tuple[str, str]]) -> PlantResult:
        """plot -> (plant, soil)."""
        return self.garden.plant(assignments, self.turn)

    def gather(self) -> GatherResult:
        result = self.garden.gather(self.turn)
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
        return self._add_potion(recipe, brew(recipe))

    def mix_all(self, mixes: Sequence[Sequence[int]]) -> list[Potion]:
        """Mix potions, all or nothing: each mix combines 2 or more distinct held potions into one
        potion brewed from their summed recipe (no plant limit); the inputs are used up. A potion may
        appear in only one mix. Raises MixError before changing anything."""
        if not mixes:
            raise MixError("Give at least one mix.")
        seen: set[int] = set()
        for i, ids in enumerate(mixes, start=1):
            where = f"Mix {i}: " if len(mixes) > 1 else ""
            if len(ids) < 2:
                raise MixError(f"{where}A mix needs at least 2 potions.")
            for pid in ids:
                potion = self.inventory.potion(pid)
                if potion is None:
                    raise MixError(f"{where}Unknown potion #{pid}.")
                if potion.used:
                    raise MixError(f"{where}Potion #{pid} was already used up.")
                if pid in seen:
                    raise MixError(f"{where}Potion #{pid} appears more than once.")
                seen.add(pid)
        return [self._mix_one(ids) for ids in mixes]

    def _mix_one(self, ids: Sequence[int]) -> Potion:
        inputs = [self.inventory.potions[pid - 1] for pid in ids]
        total: Counter[str] = Counter()
        for potion in inputs:
            total.update(potion.recipe)
            potion.used = True
        recipe = dict(total)
        return self._add_potion(recipe, effect_of(recipe), origin=tuple(ids))

    def _add_potion(self, recipe: Mapping[str, int], effect: Effect, origin: tuple[int, ...] = ()) -> Potion:
        return self.inventory.add_potion(recipe, effect, self.turn, origin)

    def deliver(self, pid: int) -> RequestResult:
        """Deliver a held potion: it is used up and the request ends, as a success or a failure.
        Raises DeliveryError (no turn cost) for an unknown or used-up potion."""
        potion = self.inventory.potion(pid)
        if potion is None:
            raise DeliveryError(f"Unknown potion #{pid}.")
        if potion.used:
            raise DeliveryError(f"Potion #{pid} was already used up.")
        potion.used = True
        self.result = judge(self.request, potion, self.turn)
        return self.result

    def log(self, potions: Mapping[int, Mapping[str, str]]) -> list[PotionLog]:
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
        return logs

    def skip(self) -> None:
        pass

    # --- free lookups --------------------------------------------------------

    def growth_records(self) -> dict[tuple[str, str], GrowthRecord]:
        """Automatic growth records: (plant, soil) pairs with at least one finished planting."""
        return self.garden.growth_records(self.turn)

    def view(self) -> GardenView:
        return garden_view(self.garden.state(self.turn), self.growth_records())

    # --- turn clock ------------------------------------------------------------

    def end_turn(self) -> None:
        """Close the request if its last turn passed without a delivery, then advance the clock."""
        if self.result is None and self.turn >= self.last_turn:
            self.result = judge(self.request, None, self.turn)
        self.turn += 1
        self.garden.settle(self.turn)  # plantings due now become ready or die
