import random

import pytest

from environment.brewer import PLANTS
from environment.garden import (
    Garden,
    GrowingPlot,
    ReadyPlot,
    sample_growth_times,
)

GROWTH = {"elderberry": 4, "sage": 2, "chamomile": 3, "basil": 6}


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
    garden.plant({1: "elderberry"}, turn=1)
    result = garden.plant({1: "sage", 2: "sage", 6: "elderberry", 3: "lavender"}, turn=2)
    assert result.planted == {2: "sage"}
    assert result.failed == {1: "occupied", 6: "does not exist", 3: "unknown plant lavender"}


def test_growth_timing():
    """Sown in turn 1 with g = 4: growing through turn 4, ready at the start of turn 5."""
    garden = Garden(1, GROWTH)
    garden.plant({1: "elderberry"}, turn=1)
    assert garden.state(1).growing == [GrowingPlot(1, "elderberry", 4)]
    assert garden.state(4).growing == [GrowingPlot(1, "elderberry", 1)]
    assert garden.state(5).ready == [ReadyPlot(1, "elderberry", 0)]
    assert garden.state(7).ready == [ReadyPlot(1, "elderberry", 2)]


def test_gather_collects_all_ready_only():
    garden = Garden(4, GROWTH)
    garden.plant({1: "sage", 2: "sage", 3: "elderberry", 4: "basil"}, turn=1)
    result = garden.gather(turn=5)          # sage ready at 3, elderberry at 5, basil at 7
    assert result.counts == {"elderberry": 1, "sage": 2}
    assert result.plots == [1, 2, 3]
    assert garden.state(5).free == [1, 2, 3]
    assert garden.state(5).growing == [GrowingPlot(4, "basil", 2)]


def test_gather_nothing_ready():
    garden = Garden(2, GROWTH)
    garden.plant({1: "basil"}, turn=1)
    result = garden.gather(turn=2)
    assert result.counts == {} and result.plots == []


def test_replant_after_gather():
    garden = Garden(1, GROWTH)
    garden.plant({1: "sage"}, turn=1)
    garden.gather(turn=3)
    assert garden.plant({1: "chamomile"}, turn=3).planted == {1: "chamomile"}
    assert garden.state(4).growing == [GrowingPlot(1, "chamomile", 2)]


def test_spec_example_turn_5():
    """The 7-plot example from demo_spec.md."""
    garden = Garden(7, GROWTH)
    garden.plant({2: "elderberry", 4: "sage"}, turn=1)   # elderberry ready at 5, sage ready at 3
    garden.plant({5: "chamomile", 7: "basil"}, turn=3)   # chamomile ready at 6, basil ready at 9
    state = garden.state(5)
    assert state.free == [1, 3, 6]
    assert state.ready == [ReadyPlot(2, "elderberry", 0), ReadyPlot(4, "sage", 2)]
    assert state.growing == [GrowingPlot(5, "chamomile", 1), GrowingPlot(7, "basil", 4)]
    assert garden.state(6).ready == [
        ReadyPlot(2, "elderberry", 1),
        ReadyPlot(4, "sage", 3),
        ReadyPlot(5, "chamomile", 0),
    ]
