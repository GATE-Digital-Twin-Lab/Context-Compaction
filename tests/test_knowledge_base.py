import pytest

from environment.brewer import PLANTS, Effect
from environment.garden import Garden
from environment.knowledge_base import KnowledgeBase, LogError, Outcome, effect_label
from environment.view import GardenView, GrowingView, ReadyView, garden_view

GROWTH = {"elderberry": 4, "sage": 2, "chamomile": 3, "basil": 6}


@pytest.fixture
def kb():
    kb = KnowledgeBase(catalogue=[(p, None) for p in PLANTS])
    yield kb
    kb.close()


def spec_garden() -> Garden:
    """7-plot example from demo_spec.md: at turn 5, 2 (elderberry) and 4 (sage, waiting 2) ready."""
    garden = Garden(7, GROWTH)
    garden.plant({2: "elderberry", 4: "sage"}, turn=1)
    garden.plant({5: "chamomile", 7: "basil"}, turn=3)
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
    labels = {"elderberry": "higher", "sage": "present", "dill": "odd"}
    assert Outcome(labels, "+I").render() == "(higher) elderberry, sage, (odd) dill → +I"
    assert Outcome({"mint": "present", "elderberry": "present", "dill": "present"}, "none").render() == (
        "mint, elderberry, dill → none"
    )


def test_garden_log_spec_example(kb):
    garden = spec_garden()
    result = kb.log_garden(garden.state(5), garden.growth_times)
    assert result.growth == {"elderberry": 4, "sage": 2}           # true values, waiting ignored
    assert result.plantings == {2: "elderberry", 4: "sage", 5: "chamomile", 7: "basil"}
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
        growing=[GrowingView(7, "basil", None)],             # basil growth time unknown
        ready=[ReadyView(2, "elderberry", 1), ReadyView(4, "sage", 3), ReadyView(5, "chamomile", 0)],
    )


def test_turns_left_once_growth_known(kb):
    garden = Garden(3, GROWTH)
    garden.plant({1: "sage"}, turn=1)
    kb.log_garden(garden.state(3), garden.growth_times)    # sage ready: growth logged
    kb.clear_plantings(garden.gather(turn=3).plots)
    garden.plant({2: "sage"}, turn=3)
    kb.log_garden(garden.state(3), garden.growth_times)    # planting of plot 2 logged
    assert garden_view(garden.state(4), kb).growing == [GrowingView(2, "sage", 1)]


def test_gather_clears_planting_records(kb):
    garden = spec_garden()
    kb.log_garden(garden.state(5), garden.growth_times)
    kb.clear_plantings(garden.gather(turn=5).plots)
    assert kb.plantings() == {5: "chamomile", 7: "basil"}
    assert kb.growth_times() == {"elderberry": 4, "sage": 2}          # growth times are permanent
    garden.plant({2: "basil"}, turn=6)
    assert garden_view(garden.state(6), kb).growing[0] == GrowingView(2, None, None)


def test_outcomes_spec_example(kb):
    """Potions #1–#4 from demo_spec.md: append-only, exact duplicates dropped."""
    present = {"elderberry": "present", "sage": "present", "dill": "present"}
    assert kb.log_outcome({"mint": "present", "elderberry": "present", "dill": "present"}, "none", 1, 21)
    assert kb.log_outcome(present, "+I", 2, 21)
    assert kb.log_outcome({**present, "elderberry": "higher"}, "+I", 3, 21)
    assert kb.log_outcome({"elderberry": "higher", "sage": "present", "dill": "odd"}, "+I", 4, 25)
    assert not kb.log_outcome({"dill": "present", "sage": "present", "elderberry": "higher"}, "+I", 3, 26)
    assert [o.render() for o in kb.outcomes("elderberry")] == [
        "dill, elderberry, mint → none",
        "dill, elderberry, sage → +I",
        "dill, (higher) elderberry, sage → +I",
        "(odd) dill, (higher) elderberry, sage → +I",
    ]
    assert len(kb.outcomes("sage")) == 3
    assert kb.outcomes("rosemary") == []


def test_invalid_label(kb):
    with pytest.raises(LogError, match='Invalid label "big"'):
        kb.log_outcome({"elderberry": "big", "sage": "present", "dill": "present"}, "+I", 1, 1)
    assert kb.outcomes() == []
