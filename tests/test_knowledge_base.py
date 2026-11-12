import pytest

from environment.brewer import PLANTS, Effect
from environment.knowledge_base import KnowledgeBase, LogError, Outcome, effect_label

@pytest.fixture
def kb():
    kb = KnowledgeBase(catalogue=PLANTS)
    yield kb
    kb.close()


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
