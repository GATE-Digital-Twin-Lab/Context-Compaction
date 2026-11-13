"""The complete world state: garden, inventory (with the potion records), the request and the turn clock."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from environment.brewer import Effect, RecipeError, brew, effect_of, validate_recipe
from environment.garden import Garden, GatherResult, GrowthRecord, PlantResult
from environment.inventory import Inventory, Potion
from environment.records import Record, RecordBook
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


@dataclass
class World:
    garden: Garden
    inventory: Inventory
    request: Request
    turn_cap: int
    turn: int = 1
    result: RequestResult | None = None  # set by the delivery, or when time runs out
    records: RecordBook = field(default_factory=RecordBook)  # the agent's claims, beliefs and requirements

    @classmethod
    def create(
        cls,
        size: int,
        request: Request,
        turn_cap: int,
        seed: int,
    ) -> "World":
        if turn_cap < 1:
            raise ValueError("The turn cap must be >= 1.")
        return cls(Garden(size, seed), Inventory(), request, turn_cap)

    def to_dict(self) -> dict:
        """Complete state."""
        return {
            "garden": self.garden.to_dict(),
            "inventory": self.inventory.to_dict(),
            "records": self.records.to_dict(),
            "request": self.request.to_dict(),
            "turn_cap": self.turn_cap,
            "turn": self.turn,
            "result": self.result.to_dict() if self.result else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "World":
        return cls(
            garden=Garden.from_dict(data["garden"]),
            inventory=Inventory.from_dict(data["inventory"]),
            records=RecordBook.from_dict(data["records"]),
            request=Request.from_dict(data["request"]),
            turn_cap=data["turn_cap"],
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

    def skip(self) -> None:
        pass

    # --- free tools that write --------------------------------------------------

    def record(self, batch) -> list[Record]:
        """Write the agent's records (all or nothing). Raises RecordError."""
        return self.records.add(batch, self.turn)

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
