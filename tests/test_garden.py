import itertools

import pytest

from environment.brewer import PLANTS
from environment.garden import DiedPlot, Garden, GrowingPlot, GrowthRecord, ReadyPlot
from environment.soils import SOIL_TABLE, SOILS, survival, survives
from environment.view import GrowingView, garden_view

# Used below (from the soil table): sage yellow 2, sage brown 5, elderberry black 5, chamomile yellow 3,
# basil brown 6; nettle black dies after 4, elderberry brown dies after 2; dill brown 2 turns, 75%.


# --- the soil table ---------------------------------------------------------------


def test_soil_table_follows_the_design():
    assert set(SOIL_TABLE) == set(PLANTS) and all(set(row) == set(SOILS) for row in SOIL_TABLE.values())
    cells = [(p, s, *SOIL_TABLE[p][s]) for p in PLANTS for s in SOILS]
    assert all(2 <= g <= 6 for *_, g, _ in cells)
    dying = [(p, s) for p, s, _, chance in cells if chance < 100]
    assert len(dying) == 8
    assert all(sum(s == soil for _, s in dying) <= 3 for soil in SOILS)
    assert all(any(survival(p, s) == 100 for s in SOILS) for p in PLANTS)   # a safe soil for every plant
    assert [(p, s, g, c) for p, s, g, c in cells if 0 < c < 100] == [("dill", "brown", 2, 75)]


def test_survival_rolls_are_reproducible_and_near_the_chance():
    rolls = [survives("dill", "brown", seed=0, plot=plot, turn=turn) for plot, turn in itertools.product(range(1, 21), range(1, 51))]
    assert rolls == [survives("dill", "brown", 0, plot, turn) for plot, turn in itertools.product(range(1, 21), range(1, 51))]
    assert 0.70 <= sum(rolls) / len(rolls) <= 0.80
    assert survives("sage", "yellow", 0, 1, 1) and not survives("nettle", "black", 0, 1, 1)


# --- planting, growing, dying --------------------------------------------------------


def test_invalid_size():
    with pytest.raises(ValueError):
        Garden(0)


def test_plant_partial_success():
    garden = Garden(5)
    garden.plant({1: ("elderberry", "black")}, turn=1)
    result = garden.plant(
        {1: ("sage", "yellow"), 2: ("sage", "yellow"), 6: ("elderberry", "black"), 3: ("lavender", "black"),
         4: ("sage", "red")},
        turn=2,
    )
    assert result.planted == {2: ("sage", "yellow")}
    assert result.failed == {1: "occupied", 6: "does not exist", 3: "unknown plant lavender", 4: "unknown soil red"}


def test_growth_time_depends_on_the_soil():
    """Sage sown in turn 1: yellow (2) ready at turn 3, brown (5) ready at turn 6."""
    garden = Garden(2)
    garden.plant({1: ("sage", "yellow"), 2: ("sage", "brown")}, turn=1)
    assert garden.state(1).growing == [GrowingPlot(1, "sage", "yellow", 1, 2), GrowingPlot(2, "sage", "brown", 1, 5)]
    assert garden.state(3).ready == [ReadyPlot(1, "sage", "yellow", 0)]
    assert garden.state(6).ready == [ReadyPlot(1, "sage", "yellow", 3), ReadyPlot(2, "sage", "brown", 0)]


def test_a_dead_plant_occupies_its_plot_until_gathered():
    garden = Garden(2)
    garden.plant({1: ("nettle", "black"), 2: ("elderberry", "black")}, turn=1)   # nettle dies after 4
    assert [g.plot for g in garden.state(4).growing] == [1, 2]
    assert garden.state(5).died == [DiedPlot(1, "nettle", "black")] and garden.state(5).free == []
    assert garden.state(9).died == [DiedPlot(1, "nettle", "black")]               # still there
    assert garden.plant({1: ("nettle", "yellow")}, turn=9).failed == {1: "occupied"}
    result = garden.gather(turn=9)
    assert result.counts == {"elderberry": 1} and result.plots == [1, 2] and result.cleared == [1]
    assert garden.state(9).free == [1, 2] and garden.state(9).died == []
    assert len(garden.history) == 2                                               # recorded once each


def test_gather_collects_all_ready_only():
    garden = Garden(4)
    garden.plant({1: ("sage", "yellow"), 2: ("sage", "yellow"), 3: ("elderberry", "black"), 4: ("basil", "brown")}, turn=1)
    result = garden.gather(turn=6)          # sage ready at 3, elderberry at 6, basil at 7
    assert result.counts == {"elderberry": 1, "sage": 2} and result.plots == [1, 2, 3]
    assert garden.state(6).free == [1, 2, 3]
    assert garden.state(6).growing == [GrowingPlot(4, "basil", "brown", 1, 1)]


def test_gather_nothing_ready():
    garden = Garden(2)
    garden.plant({1: ("basil", "brown")}, turn=1)
    result = garden.gather(turn=2)
    assert result.counts == {} and result.plots == []


def test_spec_example():
    """The garden line of demo_spec.md (day 3, turn 24), with the soil table's growth times."""
    garden = Garden(6)
    garden.plant({5: ("basil", "black")}, turn=18)       # dies after 6: reported at 24
    garden.plant({4: ("nettle", "yellow")}, turn=19)     # ready at 24
    garden.plant({2: ("sage", "yellow")}, turn=23)       # ready at 25
    garden.plant({3: ("mint", "black")}, turn=22)        # ready at 28
    state = garden.state(24)
    assert state.free == [1, 6]
    assert state.growing == [GrowingPlot(2, "sage", "yellow", 23, 1), GrowingPlot(3, "mint", "black", 22, 4)]
    assert state.ready == [ReadyPlot(4, "nettle", "yellow", 0)]
    assert state.died == [DiedPlot(5, "basil", "black")]


# --- growth records and the agent's view -----------------------------------------------


def test_growth_records_count_plantings_by_soil():
    garden = Garden(4)
    garden.plant({1: ("sage", "yellow"), 2: ("nettle", "black")}, turn=1)
    assert garden.growth_records(2) == {}
    garden.gather(turn=3)
    garden.plant({1: ("sage", "yellow"), 3: ("sage", "brown")}, turn=3)
    assert garden.growth_records(5) == {
        ("nettle", "black"): GrowthRecord("nettle", "black", 4, 1, 0, 1, 5),
        ("sage", "yellow"): GrowthRecord("sage", "yellow", 2, 2, 2, 0, 3),   # second planting ready at 5
    }
    assert ("sage", "brown") not in garden.growth_records(7)   # brown sage ready only at 8


def test_view_shows_turns_left_once_the_pair_has_finished():
    garden = Garden(3)
    garden.plant({1: ("sage", "yellow")}, turn=1)
    garden.plant({2: ("sage", "brown")}, turn=2)
    view = garden_view(garden.state(2), garden.growth_records(2))
    assert view.growing == [GrowingView(1, "sage", "yellow", 1, None), GrowingView(2, "sage", "brown", 2, None)]
    garden.gather(turn=3)
    garden.plant({1: ("sage", "yellow")}, turn=3)
    view = garden_view(garden.state(4), garden.growth_records(4))
    assert view.growing == [GrowingView(1, "sage", "yellow", 3, 1), GrowingView(2, "sage", "brown", 2, None)]


def test_checkpoint_round_trip_keeps_the_hidden_outcomes():
    garden = Garden(4, seed=3)
    garden.plant({p: ("dill", "brown") for p in range(1, 5)}, turn=1)
    copy = Garden.from_dict(garden.to_dict())
    assert copy.state(3) == garden.state(3) and copy.history == garden.history
