"""Garden plots with soils. Holds the true state, not the agent's view."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import astuple, dataclass, field, replace
from typing import NamedTuple

from environment.soils import SOIL_TABLE, SOILS, growth_time, survives


class GrowingPlot(NamedTuple):
    plot: int
    plant: str
    soil: str
    planted_turn: int
    turns_left: int


class ReadyPlot(NamedTuple):
    plot: int
    plant: str
    soil: str
    waiting: int


class DiedPlot(NamedTuple):
    plot: int
    plant: str
    soil: str


@dataclass(frozen=True)
class GardenState:
    """True garden state at one turn (plots sorted by number). A dead plant occupies its plot until gathered."""

    free: list[int]
    growing: list[GrowingPlot]
    ready: list[ReadyPlot]
    died: list[DiedPlot]


@dataclass(frozen=True)
class PlantResult:
    planted: dict[int, tuple[str, str]]  # plot -> (plant, soil)
    failed: dict[int, str]               # plot -> reason


@dataclass(frozen=True)
class GatherResult:
    counts: dict[str, int]   # plant -> number gathered
    plots: list[int]         # plots that were gathered or cleared (now free)
    cleared: list[int]       # plots whose dead plant was removed


@dataclass(frozen=True)
class Finished:
    """A planting that became ready or died (at done_turn = planted_turn + growth time)."""

    plot: int
    plant: str
    soil: str
    planted_turn: int
    done_turn: int
    survived: bool


@dataclass(frozen=True)
class GrowthRecord:
    """What the plantings of one (plant, soil) pair have shown so far."""

    plant: str
    soil: str
    turns: int     # growth time
    planted: int   # all plantings so far, including those still growing
    grew: int
    died: int
    first_turn: int  # turn the first planting finished


@dataclass
class _Plot:
    plant: str
    soil: str
    planted_turn: int
    ready_turn: int
    survives: bool
    finished: bool = False  # became ready or died; stays in the plot until gathered


@dataclass
class Garden:
    """N plots numbered 1..N. A plant sown in soil s in turn t finishes at the start of turn t + g(plant, s):
    it becomes ready, or it dies. Either way it occupies the plot until gathered. seed drives the survival rolls."""

    size: int
    seed: int = 0
    _plots: dict[int, _Plot] = field(default_factory=dict, init=False, repr=False)
    history: list[Finished] = field(default_factory=list, init=False, repr=False)  # up to the last settle()

    def __post_init__(self) -> None:
        if self.size < 1:
            raise ValueError(f"Garden size must be >= 1, got {self.size}.")

    def settle(self, turn: int) -> None:
        """Finish every planting due by this turn (idempotent) and record it."""
        for plot, slot in sorted(self._plots.items()):
            if slot.finished or slot.ready_turn > turn:
                continue
            self.history.append(Finished(plot, slot.plant, slot.soil, slot.planted_turn, slot.ready_turn, slot.survives))
            slot.finished = True

    def plant(self, assignments: Mapping[int, tuple[str, str]], turn: int) -> PlantResult:
        """Plant every valid plot (plot -> (plant, soil)); report the others with a reason (partial success)."""
        self.settle(turn)
        planted: dict[int, tuple[str, str]] = {}
        failed: dict[int, str] = {}
        for plot, (plant, soil) in assignments.items():
            if not 1 <= plot <= self.size:
                failed[plot] = "does not exist"
            elif plant not in SOIL_TABLE:
                failed[plot] = f"unknown plant {plant}"
            elif soil not in SOILS:
                failed[plot] = f"unknown soil {soil}"
            elif plot in self._plots:
                failed[plot] = "occupied"
            else:
                lives = survives(plant, soil, self.seed, plot, turn)
                self._plots[plot] = _Plot(plant, soil, turn, turn + growth_time(plant, soil), lives)
                planted[plot] = (plant, soil)
        return PlantResult(planted, failed)

    def gather(self, turn: int) -> GatherResult:
        """Harvest all ready plots, clear all dead plants, and free those plots. Never fails."""
        self.settle(turn)
        done = [p for p, slot in sorted(self._plots.items()) if slot.finished]
        removed = {p: self._plots.pop(p) for p in done}
        counts = Counter(slot.plant for slot in removed.values() if slot.survives)
        cleared = [p for p, slot in removed.items() if not slot.survives]
        return GatherResult(dict(sorted(counts.items())), done, cleared)

    def state(self, turn: int) -> GardenState:
        """Free, growing, ready and died plots at the given turn."""
        self.settle(turn)
        free, growing, ready, died = [], [], [], []
        for plot in range(1, self.size + 1):
            slot = self._plots.get(plot)
            if slot is None:
                free.append(plot)
            elif not slot.finished:
                growing.append(GrowingPlot(plot, slot.plant, slot.soil, slot.planted_turn, slot.ready_turn - turn))
            elif slot.survives:
                ready.append(ReadyPlot(plot, slot.plant, slot.soil, turn - slot.ready_turn))
            else:
                died.append(DiedPlot(plot, slot.plant, slot.soil))
        return GardenState(free, growing, ready, died)

    def plantings(self) -> dict[int, tuple[str, str, int]]:
        """Occupied plots: plot -> (plant, soil, turn it was planted)."""
        return {p: (s.plant, s.soil, s.planted_turn) for p, s in sorted(self._plots.items())}

    def growth_records(self, turn: int) -> dict[tuple[str, str], GrowthRecord]:
        """(plant, soil) -> record, for every pair with at least one finished planting."""
        self.settle(turn)
        records: dict[tuple[str, str], GrowthRecord] = {}
        for f in self.history:
            key = (f.plant, f.soil)
            old = records.get(key) or GrowthRecord(f.plant, f.soil, f.done_turn - f.planted_turn, 0, 0, 0, f.done_turn)
            records[key] = replace(
                old, planted=old.planted + 1, grew=old.grew + f.survived, died=old.died + (not f.survived)
            )
        for slot in self._plots.values():
            if not slot.finished and (key := (slot.plant, slot.soil)) in records:
                records[key] = replace(records[key], planted=records[key].planted + 1)
        return dict(sorted(records.items()))

    def to_dict(self) -> dict:
        plots = {str(p): list(astuple(s)) for p, s in sorted(self._plots.items())}
        return {"size": self.size, "seed": self.seed, "plots": plots, "history": [list(astuple(f)) for f in self.history]}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Garden":
        garden = cls(data["size"], data["seed"])
        garden._plots = {int(p): _Plot(*slot) for p, slot in data["plots"].items()}
        garden.history = [Finished(*f) for f in data["history"]]
        return garden
