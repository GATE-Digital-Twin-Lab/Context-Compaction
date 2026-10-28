import itertools

import pytest

from environment.brewer import STAT_SETS, Effect, RecipeError, brew, intensity


def ones(stat: str) -> dict[str, int]:
    return {p: 1 for p in STAT_SETS[stat]}


@pytest.mark.parametrize(
    "score, level", [(-1, 0), (0, 0), (1, 2), (2, 5), (3, 10), (4, 20), (9, 20)]
)
def test_intensity(score, level):
    assert intensity(score) == level


@pytest.mark.parametrize(
    "recipe",
    [
        {"mint": 1, "elderberry": 1},                                 # too few plants
        {"mint": 1, "elderberry": 1, "nettle": 1, "sage": 1, "chamomile": 1},      # too many plants
        {"mint": 1, "elderberry": 1, "lavender": 1},                        # unknown plant
        {"mint": 0, "elderberry": 1, "nettle": 1},                        # zero count
        {"mint": 1.5, "elderberry": 1, "nettle": 1},                      # non-integer count
    ],
)
def test_invalid_recipes(recipe):
    with pytest.raises(RecipeError):
        brew(recipe)


@pytest.mark.parametrize(
    "stat, expected",
    [
        ("I", Effect({"I": 2}, {})),
        ("S", Effect({}, {"S": 2})),
        ("V", Effect()),
        ("D", Effect({"D": 2}, {})),
        ("W", Effect()),
    ],
)
def test_all_ones(stat, expected):
    assert brew(ones(stat)) == expected


@pytest.mark.parametrize(
    "stat, pos, neg, empty",
    [
        ("I", 72, 36, 108),
        ("S", 6, 102, 108),
        ("V", 75, 21, 120),
        ("D", 72, 108, 36),
        ("W", 54, 270, 972),
    ],
)
def test_outcome_counts(stat, pos, neg, empty):
    """Counts 1–6 per plant reproduce the brute-force table in demo_spec.md."""
    plants = STAT_SETS[stat]
    counts = {"+": 0, "-": 0, "0": 0}
    for combo in itertools.product(range(1, 7), repeat=len(plants)):
        effect = brew(dict(zip(plants, combo)))
        counts["+" if effect.positive else "-" if effect.negative else "0"] += 1
    assert counts == {"+": pos, "-": neg, "0": empty}


@pytest.mark.parametrize(
    "stat, recipe",
    [
        ("I", {"elderberry": 4, "sage": 1, "dill": 1}),
        ("S", {"mint": 2, "chamomile": 4, "rosemary": 2}),
        ("V", {"mint": 1, "nettle": 2, "basil": 4}),
        ("D", {"nettle": 1, "sage": 1, "rosemary": 4}),
        ("W", {"elderberry": 2, "chamomile": 1, "dill": 4, "basil": 1}),
    ],
)
def test_cheapest_max_recipes(stat, recipe):
    assert brew(recipe) == Effect({stat: 20}, {})


@pytest.mark.parametrize(
    "recipe",
    [
        {"elderberry": 2, "sage": 3, "dill": 1},          # I: sage odd and divisible by 3
        {"mint": 2, "chamomile": 3, "rosemary": 5},          # S: rosemary = 5 is 2 mod 3 and odd
        {"mint": 2, "nettle": 2, "basil": 3},          # V: nettle even and mint = 2
        {"elderberry": 2, "chamomile": 2, "dill": 3, "basil": 1}, # W: elderberry = 2, basil odd, chamomile even
    ],
)
def test_cancellation(recipe):
    assert brew(recipe).is_empty


def test_traps():
    assert brew({"mint": 1, "nettle": 2, "basil": 5}).is_empty   # V: basil multiple of 5
    assert brew({"nettle": 1, "sage": 3, "rosemary": 1}).is_empty   # D: score <= 0


def test_no_complete_set():
    assert brew({"mint": 1, "elderberry": 1, "dill": 1}).is_empty


def test_extra_plant_does_not_change_effect():
    base = {"mint": 2, "chamomile": 4, "rosemary": 2}
    assert brew({**base, "nettle": 5}) == brew(base)


def test_to_dict():
    assert brew({"elderberry": 2, "sage": 1, "dill": 1}).to_dict() == {
        "positive": {"I": 5},
        "negative": {},
    }
