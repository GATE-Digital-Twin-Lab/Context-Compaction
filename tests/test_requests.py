import pytest

from environment.brewer import Effect
from environment.inventory import Potion
from environment.requests import Request, RequestResult, judge, load_requests


def potion(recipe, positive=None, secondary=()) -> Potion:
    return Potion(1, recipe, Effect(positive or {}, {}, tuple(secondary)), turn=5)


REQUEST = Request("r", "text", "D", threshold=25, deadline_day=7, excluded=frozenset({"basil", "mint"}))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(stat="X"),
        dict(stat="S", threshold=0),
        dict(stat="S", deadline_day=0),
        dict(stat="S", excluded=frozenset({"lavender"})),
        dict(stat="D", excluded=frozenset({"nettle"})),   # nettle is needed for D
    ],
)
def test_invalid_requests(kwargs):
    with pytest.raises(ValueError):
        Request("r", "text", **kwargs)


def test_deadline_and_translation():
    assert REQUEST.deadline_turn == 70
    assert REQUEST.describe() == "D >= +25% by day 7 (turn 70) without basil, mint"
    assert Request("r", "t", "W").describe() == "any +W" and Request("r", "t", "W").deadline_turn is None


def test_round_trip():
    assert Request.from_dict(REQUEST.to_dict()) == REQUEST
    result = RequestResult(3, 40, False, 20, ("D 20% is below 25%",))
    assert RequestResult.from_dict(result.to_dict()) == result


def test_judge_success_ignores_other_effects():
    result = judge(REQUEST, potion({"nettle": 1, "sage": 1, "rosemary": 4}, {"D": 25, "I": 5}), turn=12)
    assert result == RequestResult(1, 12, True, 25, ())


@pytest.mark.parametrize(
    "recipe, positive, secondary, failures",
    [
        ({"nettle": 1}, {"D": 20}, (), ("D 20% is below 25%",)),
        ({"nettle": 1}, {}, (), ("no positive D",)),
        ({"nettle": 1}, {"D": 40}, ("murky", "murky"), ("undrinkable",)),
        ({"nettle": 1, "mint": 1, "basil": 1}, {"D": 40}, (), ("contains basil, mint",)),
    ],
)
def test_judge_failures(recipe, positive, secondary, failures):
    result = judge(REQUEST, potion(recipe, positive, secondary), turn=12)
    assert not result.success and result.failures == failures


def test_any_positive_intensity_without_a_threshold():
    assert judge(Request("r", "t", "D"), potion({"nettle": 1}, {"D": 2}), turn=3).success


def test_nothing_delivered():
    assert judge(REQUEST, None, turn=70) == RequestResult(None, 70, False, 0, ("nothing delivered",))


def test_the_requests_file_loads():
    requests = load_requests()
    assert requests["stonecutter"].describe() == "S >= +25% by day 7 (turn 70)"
    assert requests["maiden"].describe() == "any +D without elderberry, mint"
