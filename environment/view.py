"""The agent's view of the garden: every plot shows its plant and soil; a growing plot shows the
turns left once its (plant, soil) growth time is recorded, otherwise the turn it was planted."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

from environment.garden import DiedPlot, GardenState, GrowthRecord, ReadyPlot


class GrowingView(NamedTuple):
    plot: int
    plant: str
    soil: str
    planted_turn: int
    turns_left: int | None  # only once the (plant, soil) growth time is recorded


@dataclass(frozen=True)
class GardenView:
    free: list[int]
    growing: list[GrowingView]
    ready: list[ReadyPlot]
    died: list[DiedPlot]


def garden_view(state: GardenState, records: Mapping[tuple[str, str], GrowthRecord]) -> GardenView:
    growing = [
        GrowingView(g.plot, g.plant, g.soil, g.planted_turn, g.turns_left if (g.plant, g.soil) in records else None)
        for g in state.growing
    ]
    return GardenView(list(state.free), growing, list(state.ready), list(state.died))
