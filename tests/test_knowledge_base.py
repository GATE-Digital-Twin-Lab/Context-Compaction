import pytest

from environment.brewer import PLANTS, Effect
from environment.garden import Garden
from environment.knowledge_base import KnowledgeBase, LogError, Outcome, effect_label
from environment.view import GardenView, GrowingView, ReadyView, garden_view

GROWTH = {"p2": 4, "p4": 2, "p5": 3, "p7": 6}


@pytest.fixture
def kb():
    kb = KnowledgeBase(catalogue=[(p, None) for p in PLANTS])
    yield kb
    kb.close()


def spec_garden() -> Garden:
    """7-plot example from demo_spec.md: at turn 5, 2 (p2) and 4 (p4, waiting 2) ready."""
    garden = Garden(7, GROWTH)
    garden.plant({2: "p2", 4: "p4"}, turn=1)
    garden.plant({5: "p5", 7: "p7"}, turn=3)
    return garden


def test_catalogue(kb):
    assert kb.catalogue() == sorted(PLANTS)


@pytest.mark.parametrize(
    "effect, label",
    [(Effect({"S": 20}, {}), "+S"), (Effect({}, {"I": 2}), "-I"), (Effect(), "none")],
)
def test_effect_label(effect, label):
    assert effect_label(effect) == label


def test_render():
    labels = {"p2": "higher", "p4": "present", "p6": "odd"}
    assert Outcome(labels, "+I").render() == "(higher) p2, p4, (odd) p6 → +I"
    assert Outcome({"p1": "present", "p2": "present", "p6": "present"}, "none").render() == (
        "p1, p2, p6 → none"
    )


def test_garden_log_spec_example(kb):
    garden = spec_garden()
    result = kb.log_garden(garden.state(5), garden.growth_times)
    assert result.growth == {"p2": 4, "p4": 2}           # true values, waiting ignored
    assert result.plantings == {2: "p2", 4: "p4", 5: "p5", 7: "p7"}
    again = kb.log_garden(garden.state(5), garden.growth_times)
    assert again.growth == {} and again.plantings == {}  # nothing new


def test_view_before_and_after_garden_log(kb):
    garden = spec_garden()
    assert garden_view(garden.state(5), kb) == GardenView(
        free=[1, 3, 6],
        growing=[GrowingView(5, None, None), GrowingView(7, None, None)],
        ready=[ReadyView(2, None, 0), ReadyView(4, None, 2)],
    )
    kb.log_garden(garden.state(5), garden.growth_times)
    assert garden_view(garden.state(6), kb) == GardenView(
        free=[1, 3, 6],
        growing=[GrowingView(7, "p7", None)],             # p7 growth time unknown
        ready=[ReadyView(2, "p2", 1), ReadyView(4, "p4", 3), ReadyView(5, "p5", 0)],
    )


def test_turns_left_once_growth_known(kb):
    garden = Garden(3, GROWTH)
    garden.plant({1: "p4"}, turn=1)
    kb.log_garden(garden.state(3), garden.growth_times)    # p4 ready: growth logged
    kb.clear_plantings(garden.gather(turn=3).plots)
    garden.plant({2: "p4"}, turn=3)
    kb.log_garden(garden.state(3), garden.growth_times)    # planting of plot 2 logged
    assert garden_view(garden.state(4), kb).growing == [GrowingView(2, "p4", 1)]


def test_gather_clears_planting_records(kb):
    garden = spec_garden()
    kb.log_garden(garden.state(5), garden.growth_times)
    kb.clear_plantings(garden.gather(turn=5).plots)
    assert kb.plantings() == {5: "p5", 7: "p7"}
    assert kb.growth_times() == {"p2": 4, "p4": 2}          # growth times are permanent
    garden.plant({2: "p7"}, turn=6)
    assert garden_view(garden.state(6), kb).growing[0] == GrowingView(2, None, None)


def test_outcomes_spec_example(kb):
    """Potions #1–#4 from demo_spec.md: append-only, exact duplicates dropped."""
    present = {"p2": "present", "p4": "present", "p6": "present"}
    assert kb.log_outcome({"p1": "present", "p2": "present", "p6": "present"}, "none", 1, 21)
    assert kb.log_outcome(present, "+I", 2, 21)
    assert kb.log_outcome({**present, "p2": "higher"}, "+I", 3, 21)
    assert kb.log_outcome({"p2": "higher", "p4": "present", "p6": "odd"}, "+I", 4, 25)
    assert not kb.log_outcome({"p6": "present", "p4": "present", "p2": "higher"}, "+I", 3, 26)
    assert [o.render() for o in kb.outcomes("p2")] == [
        "p1, p2, p6 → none",
        "p2, p4, p6 → +I",
        "(higher) p2, p4, p6 → +I",
        "(higher) p2, p4, (odd) p6 → +I",
    ]
    assert len(kb.outcomes("p4")) == 3
    assert kb.outcomes("p8") == []


def test_invalid_label(kb):
    with pytest.raises(LogError, match='Invalid label "big"'):
        kb.log_outcome({"p2": "big", "p4": "present", "p6": "present"}, "+I", 1, 1)
    assert kb.outcomes() == []
