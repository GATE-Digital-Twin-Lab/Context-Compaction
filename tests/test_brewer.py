import itertools

import pytest

from environment.brewer import (
    MODIFIERS,
    SECONDARY_PAIRS,
    STAT_SETS,
    Effect,
    RecipeError,
    apply_modifier,
    brew,
    effect_of,
    intensity,
    net_modifier,
    secondary_labels,
)


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
        {"mint": 1},                                                  # too few plants
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


def test_extra_plant_adds_its_pairs():
    base = {"mint": 2, "chamomile": 4, "rosemary": 2}
    assert brew({**base, "nettle": 5}) == Effect({"S": 30}, {}, ("shimmering",))   # chamomile + nettle


def test_to_dict():
    assert brew({"elderberry": 2, "sage": 1, "dill": 1}).to_dict() == {
        "positive": {"I": 5},
        "negative": {},
        "secondary": [],
    }


# --- secondary effects ----------------------------------------------------------


def test_secondary_pairs_design():
    """11 pairs, none inside a stat set; a label's pairs share no plant; toxic has a single pair."""
    inside = {frozenset(p) for s in STAT_SETS.values() for p in itertools.combinations(s, 2)}
    assert len(SECONDARY_PAIRS) == 11 and not set(SECONDARY_PAIRS) & inside
    by_label = {label: [p for p, l in SECONDARY_PAIRS.items() if l == label] for label in MODIFIERS}
    assert {label: len(pairs) for label, pairs in by_label.items()} == {
        "fragrant": 2, "shimmering": 2, "sweet": 2, "bitter": 2, "murky": 2, "toxic": 1,
    }
    assert all(not (a & b) for a, b, *_ in (ps for ps in by_label.values() if len(ps) == 2))


@pytest.mark.parametrize("stat", STAT_SETS)
def test_minimal_stat_recipe_has_no_secondary(stat):
    assert brew(ones(stat)).secondary == ()


@pytest.mark.parametrize(
    "base, modifier, value",
    [(2, 25, 3), (5, 25, 6), (2, -25, 2), (5, -50, 3), (10, 50, 15), (20, 175, 55), (20, -75, 5), (20, -100, 0)],
)
def test_apply_modifier_rounds_half_away_from_zero(base, modifier, value):
    assert apply_modifier(base, modifier) == value


def test_two_plant_probe_gives_only_a_secondary():
    assert brew({"mint": 1, "sage": 3}) == Effect({}, {}, ("fragrant",))
    assert brew({"mint": 1, "rosemary": 1}) == Effect()   # pair inside the S set


def test_same_label_twice_counts_twice():
    assert secondary_labels(["dill", "mint", "chamomile", "sage"]) == ("fragrant", "sweet", "sweet")
    assert net_modifier(("fragrant", "sweet", "sweet")) == 225


def test_modifier_applies_to_negative_effects():
    # -S 20 (rosemary odd) with sage: fragrant + sweet = +125%
    assert brew({"mint": 1, "chamomile": 4, "rosemary": 1, "sage": 1}) == Effect({}, {"S": 45}, ("fragrant", "sweet"))


def test_positive_and_negative_modifiers_cancel():
    effect = brew({"mint": 2, "chamomile": 4, "rosemary": 2, "dill": 1})
    assert effect == Effect({"S": 20}, {}, ("sweet", "bitter")) and effect.drinkable


def test_toxic_removes_the_effect():
    effect = brew({"mint": 1, "nettle": 2, "basil": 4, "elderberry": 1})   # V 20 + bitter + toxic
    assert effect == Effect({}, {}, ("bitter", "toxic")) and not effect.drinkable


def test_positive_pair_is_an_antidote():
    effect = brew({"elderberry": 1, "nettle": 1, "chamomile": 1})
    assert effect.secondary == ("shimmering", "toxic") and effect.drinkable


def test_net_minus_100_is_undrinkable_without_toxic():
    assert not Effect(secondary=("murky", "murky")).drinkable
    assert Effect(secondary=("murky", "bitter")).drinkable


def test_from_dict_without_secondary():
    assert Effect.from_dict({"positive": {"S": 5}, "negative": {}}) == Effect({"S": 5}, {})


# --- mixing (summed recipes) -------------------------------------------------------


def test_effect_of_has_no_plant_limit_and_several_stats():
    recipe = {"elderberry": 4, "sage": 1, "dill": 1, "mint": 2, "chamomile": 4, "rosemary": 2}
    effect = effect_of(recipe)
    assert effect.positive == {"I": 20, "S": 20} and effect.negative == {}
    assert effect.secondary == ("fragrant", "sweet", "sweet", "bitter", "bitter", "murky")   # mixed signs cancel
    with pytest.raises(RecipeError):
        brew(recipe)


def test_added_plants_can_break_a_primary_condition():
    assert brew({"elderberry": 4, "sage": 1, "dill": 1}).positive == {"I": 20}
    assert effect_of({"elderberry": 4, "sage": 3, "dill": 1}).is_empty   # sage odd and divisible by 3: cancel
