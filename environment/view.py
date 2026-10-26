"""The agent's view of the garden: names and turns left only where logged."""

from dataclasses import dataclass
from typing import NamedTuple

from environment.garden import GardenState
from environment.knowledge_base import KnowledgeBase


class GrowingView(NamedTuple):
    plot: int
    plant: str | None       # only if the planting is logged
    turns_left: int | None  # only if the planting and the growth time are logged


class ReadyView(NamedTuple):
    plot: int
    plant: str | None
    waiting: int


@dataclass(frozen=True)
class GardenView:
    free: list[int]
    growing: list[GrowingView]
    ready: list[ReadyView]


def garden_view(state: GardenState, kb: KnowledgeBase) -> GardenView:
    plantings = kb.plantings()
    growth = kb.growth_times()
    growing = []
    for g in state.growing:
        plant = plantings.get(g.plot)
        known = plant is not None and plant in growth
        growing.append(GrowingView(g.plot, plant, g.turns_left if known else None))
    ready = [ReadyView(r.plot, plantings.get(r.plot), r.waiting) for r in state.ready]
    return GardenView(list(state.free), growing, ready)
