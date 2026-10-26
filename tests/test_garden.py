import random

import pytest

from environment.brewer import PLANTS
from environment.garden import (
    Garden,
    GrowingPlot,
    ReadyPlot,
    sample_growth_times,
)

GROWTH = {"p2": 4, "p4": 2, "p5": 3, "p7": 6}


def test_sample_growth_times_range_and_seed():
    times = sample_growth_times(PLANTS, 2, 6, random.Random(0))
    assert set(times) == set(PLANTS)
    assert all(2 <= g <= 6 for g in times.values())
    assert times == sample_growth_times(PLANTS, 2, 6, random.Random(0))


@pytest.mark.parametrize("a, b", [(0, 3), (5, 2)])
def test_sample_growth_times_invalid(a, b):
    with pytest.raises(ValueError):
        sample_growth_times(PLANTS, a, b, random.Random(0))


def test_invalid_size():
    with pytest.raises(ValueError):
        Garden(0, GROWTH)


def test_plant_partial_success():
    garden = Garden(5, GROWTH)
    garden.plant({1: "p2"}, turn=1)
    result = garden.plant({1: "p4", 2: "p4", 6: "p2", 3: "p9"}, turn=2)
    assert result.planted == {2: "p4"}
    assert result.failed == {1: "occupied", 6: "does not exist", 3: "unknown plant p9"}


def test_growth_timing():
    """Sown in turn 1 with g = 4: growing through turn 4, ready at the start of turn 5."""
    garden = Garden(1, GROWTH)
    garden.plant({1: "p2"}, turn=1)
    assert garden.state(1).growing == [GrowingPlot(1, "p2", 4)]
    assert garden.state(4).growing == [GrowingPlot(1, "p2", 1)]
    assert garden.state(5).ready == [ReadyPlot(1, "p2", 0)]
    assert garden.state(7).ready == [ReadyPlot(1, "p2", 2)]


def test_gather_collects_all_ready_only():
    garden = Garden(4, GROWTH)
    garden.plant({1: "p4", 2: "p4", 3: "p2", 4: "p7"}, turn=1)
    result = garden.gather(turn=5)          # p4 ready at 3, p2 at 5, p7 at 7
    assert result.counts == {"p2": 1, "p4": 2}
    assert result.plots == [1, 2, 3]
    assert garden.state(5).free == [1, 2, 3]
    assert garden.state(5).growing == [GrowingPlot(4, "p7", 2)]


def test_gather_nothing_ready():
    garden = Garden(2, GROWTH)
    garden.plant({1: "p7"}, turn=1)
    result = garden.gather(turn=2)
    assert result.counts == {} and result.plots == []


def test_replant_after_gather():
    garden = Garden(1, GROWTH)
    garden.plant({1: "p4"}, turn=1)
    garden.gather(turn=3)
    assert garden.plant({1: "p5"}, turn=3).planted == {1: "p5"}
    assert garden.state(4).growing == [GrowingPlot(1, "p5", 2)]


def test_spec_example_turn_5():
    """The 7-plot example from demo_spec.md."""
    garden = Garden(7, GROWTH)
    garden.plant({2: "p2", 4: "p4"}, turn=1)   # p2 ready at 5, p4 ready at 3
    garden.plant({5: "p5", 7: "p7"}, turn=3)   # p5 ready at 6, p7 ready at 9
    state = garden.state(5)
    assert state.free == [1, 3, 6]
    assert state.ready == [ReadyPlot(2, "p2", 0), ReadyPlot(4, "p4", 2)]
    assert state.growing == [GrowingPlot(5, "p5", 1), GrowingPlot(7, "p7", 4)]
    assert garden.state(6).ready == [
        ReadyPlot(2, "p2", 1),
        ReadyPlot(4, "p4", 3),
        ReadyPlot(5, "p5", 0),
    ]
