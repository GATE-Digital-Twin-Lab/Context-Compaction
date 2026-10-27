"""Garden plots and hidden growth times. Holds the true state, not the agent's view."""

import random
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import NamedTuple


def sample_growth_times(
    plants: Iterable[str], a: int, b: int, rng: random.Random
) -> dict[str, int]:
    """Sample each plant's growth time from the discrete uniform U(a, b)."""
    if not 1 <= a <= b:
        raise ValueError(f"Need 1 <= a <= b, got a={a}, b={b}.")
    return {plant: rng.randint(a, b) for plant in plants}


class GrowingPlot(NamedTuple):
    plot: int
    plant: str
    turns_left: int


class ReadyPlot(NamedTuple):
    plot: int
    plant: str
    waiting: int


@dataclass(frozen=True)
class GardenState:
    """True garden state at one turn (plots sorted by number)."""

    free: list[int]
    growing: list[GrowingPlot]
    ready: list[ReadyPlot]


@dataclass(frozen=True)
class PlantResult:
    planted: dict[int, str]  # plot -> plant
    failed: dict[int, str]   # plot -> reason


@dataclass(frozen=True)
class GatherResult:
    counts: dict[str, int]   # plant -> number gathered
    plots: list[int]         # plots that were gathered (now free)


@dataclass
class _Plot:
    plant: str
    planted_turn: int
    ready_turn: int


@dataclass
class Garden:
    """N plots numbered 1..N; a plant sown in turn t is ready at the start of turn t + g."""

    size: int
    growth_times: dict[str, int]
    _plots: dict[int, _Plot] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.size < 1:
            raise ValueError(f"Garden size must be >= 1, got {self.size}.")

    def plant(self, assignments: Mapping[int, str], turn: int) -> PlantResult:
        """Plant every valid plot; report the others with a reason (partial success)."""
        planted: dict[int, str] = {}
        failed: dict[int, str] = {}
        for plot, plant in assignments.items():
            if not 1 <= plot <= self.size:
                failed[plot] = "does not exist"
            elif plant not in self.growth_times:
                failed[plot] = f"unknown plant {plant}"
            elif plot in self._plots:
                failed[plot] = "occupied"
            else:
                self._plots[plot] = _Plot(plant, turn, turn + self.growth_times[plant])
                planted[plot] = plant
        return PlantResult(planted, failed)

    def to_dict(self) -> dict:
        plots = {str(p): [s.plant, s.planted_turn, s.ready_turn] for p, s in sorted(self._plots.items())}
        return {"size": self.size, "growth_times": self.growth_times, "plots": plots}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Garden":
        garden = cls(data["size"], dict(data["growth_times"]))
        garden._plots = {int(p): _Plot(*slot) for p, slot in data["plots"].items()}
        return garden

    def plantings(self) -> dict[int, tuple[str, int]]:
        """Occupied plots: plot -> (plant, turn it was planted)."""
        return {p: (s.plant, s.planted_turn) for p, s in sorted(self._plots.items())}

    def gather(self, turn: int) -> GatherResult:
        """Harvest all ready plots and free them. Never fails."""
        ready = [p for p, slot in sorted(self._plots.items()) if turn >= slot.ready_turn]
        counts = Counter(self._plots.pop(p).plant for p in ready)
        return GatherResult(dict(sorted(counts.items())), ready)

    def state(self, turn: int) -> GardenState:
        """Free, growing and ready plots at the given turn."""
        free, growing, ready = [], [], []
        for plot in range(1, self.size + 1):
            slot = self._plots.get(plot)
            if slot is None:
                free.append(plot)
            elif turn >= slot.ready_turn:
                ready.append(ReadyPlot(plot, slot.plant, turn - slot.ready_turn))
            else:
                growing.append(GrowingPlot(plot, slot.plant, slot.ready_turn - turn))
        return GardenState(free, growing, ready)
