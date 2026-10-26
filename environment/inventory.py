"""Plants and brewed potions. Potion details are hidden from the agent's view."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from environment.brewer import Effect


@dataclass
class Potion:
    """A brewed potion (a no-effect brew is a potion too)."""

    id: int
    recipe: dict[str, int]
    effect: Effect
    turn: int
    logged: bool = False


@dataclass
class Inventory:
    plants: Counter[str] = field(default_factory=Counter)
    potions: list[Potion] = field(default_factory=list)

    def add_plants(self, counts: Mapping[str, int]) -> None:
        self.plants.update(counts)

    def shortages(self, recipe: Mapping[str, int]) -> dict[str, tuple[int, int]]:
        """Plants the recipe needs but the inventory lacks: plant -> (need, have)."""
        return {
            p: (n, self.plants[p]) for p, n in recipe.items() if self.plants[p] < n
        }

    def consume(self, recipe: Mapping[str, int]) -> None:
        if self.shortages(recipe):
            raise ValueError("Not enough plants for this recipe.")
        self.plants.subtract(recipe)
        self.plants = +self.plants  # drop zero counts

    def add_potion(self, recipe: Mapping[str, int], effect: Effect, turn: int) -> Potion:
        potion = Potion(len(self.potions) + 1, dict(recipe), effect, turn)
        self.potions.append(potion)
        return potion
