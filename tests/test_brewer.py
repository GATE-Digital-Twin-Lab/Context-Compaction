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
        {"p1": 1, "p2": 1},                                 # too few plants
        {"p1": 1, "p2": 1, "p3": 1, "p4": 1, "p5": 1},      # too many plants
        {"p1": 1, "p2": 1, "p9": 1},                        # unknown plant
        {"p1": 0, "p2": 1, "p3": 1},                        # zero count
        {"p1": 1.5, "p2": 1, "p3": 1},                      # non-integer count
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
        ("I", {"p2": 4, "p4": 1, "p6": 1}),
        ("S", {"p1": 2, "p5": 4, "p8": 2}),
        ("V", {"p1": 1, "p3": 2, "p7": 4}),
        ("D", {"p3": 1, "p4": 1, "p8": 4}),
        ("W", {"p2": 2, "p5": 1, "p6": 4, "p7": 1}),
    ],
)
def test_cheapest_max_recipes(stat, recipe):
    assert brew(recipe) == Effect({stat: 20}, {})


@pytest.mark.parametrize(
    "recipe",
    [
        {"p2": 2, "p4": 3, "p6": 1},          # I: p4 odd and divisible by 3
        {"p1": 2, "p5": 3, "p8": 5},          # S: p8 = 5 is 2 mod 3 and odd
        {"p1": 2, "p3": 2, "p7": 3},          # V: p3 even and p1 = 2
        {"p2": 2, "p5": 2, "p6": 3, "p7": 1}, # W: p2 = 2, p7 odd, p5 even
    ],
)
def test_cancellation(recipe):
    assert brew(recipe).is_empty


def test_traps():
    assert brew({"p1": 1, "p3": 2, "p7": 5}).is_empty   # V: p7 multiple of 5
    assert brew({"p3": 1, "p4": 3, "p8": 1}).is_empty   # D: score <= 0


def test_no_complete_set():
    assert brew({"p1": 1, "p2": 1, "p6": 1}).is_empty


def test_extra_plant_does_not_change_effect():
    base = {"p1": 2, "p5": 4, "p8": 2}
    assert brew({**base, "p3": 5}) == brew(base)


def test_to_dict():
    assert brew({"p2": 2, "p4": 1, "p6": 1}).to_dict() == {
        "positive": {"I": 5},
        "negative": {},
    }
