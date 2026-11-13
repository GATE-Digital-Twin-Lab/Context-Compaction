import pytest

from environment.brewer import effect_of
from environment.garden import Finished
from environment.inventory import Potion
from environment.notebook import parse_pattern
from environment.validator import check, wilson


def brewed(*recipes) -> list[Potion]:
    """Potions #1, #2, ... with their real effects."""
    return [Potion(i, dict(r), effect_of(r), turn=1) for i, r in enumerate(recipes, start=1)]


def ask(statement, potions=(), history=()):
    return check(statement, list(potions), list(history))


# --- patterns ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern, recipe, match",
    [
        ({"mint": 2, "sage": "any"}, {"mint": 2, "sage": 3, "dill": 1}, True),
        ({"mint": 2}, {"mint": 3}, False),
        ({"sage": "odd"}, {"sage": 3}, True),
        ({"sage": "odd"}, {"sage": 2}, False),
        ({"sage": "even"}, {"mint": 1}, False),          # a condition other than absent needs the plant
        ({"nettle": "absent", "sage": "any"}, {"sage": 1}, True),
        ({"sage": "any", "only": True}, {"sage": 1, "mint": 1}, False),
        ({"sage": "any", "mint": "any", "only": True}, {"sage": 1, "mint": 1}, True),
    ],
)
def test_patterns(pattern, recipe, match):
    assert parse_pattern(pattern).matches(recipe) is match


@pytest.mark.parametrize("pattern", [{}, {"lavender": 1}, {"mint": 0}, {"mint": "some"}, {"mint": True}, {"mint": 1, "only": 1}])
def test_invalid_patterns(pattern):
    with pytest.raises(ValueError):
        parse_pattern(pattern)


# --- sufficiency and necessity ------------------------------------------------------------------


POTIONS = brewed(
    {"sage": 1, "chamomile": 1},                              # 1 sweet
    {"sage": 2, "chamomile": 3, "mint": 1},                   # 2 sweet, fragrant
    {"mint": 1, "dill": 1},                                   # 3 sweet
    {"mint": 1, "rosemary": 1},                               # 4 nothing
    {"nettle": 1, "sage": 1, "rosemary": 2},                  # 5 +D 5
    {"nettle": 2, "sage": 1, "rosemary": 2, "basil": 1},      # 6 +D 9 (5 × 1.75): fragrant, warming
)


def test_sufficiency_true_false_unknown():
    assert ask({"kind": "sufficiency", "pattern": {"sage": "any", "chamomile": "any"}, "effect": "sweet"}, POTIONS) == {
        "status": "true", "for": [1, 2], "against": [], "tested": 2}
    false = ask({"kind": "sufficiency", "pattern": {"mint": "any"}, "effect": "sweet"}, POTIONS)
    assert false["status"] == "false" and false["against"] == [4] and false["tested"] == 3
    assert ask({"kind": "sufficiency", "pattern": {"basil": 2}, "effect": "+D"}, POTIONS)["status"] == "unknown"


def test_effects_with_minimum_and_negation():
    assert ask({"kind": "sufficiency", "pattern": {"nettle": "any"}, "effect": "+D", "at_least": 9}, POTIONS)["against"] == [5]
    assert ask({"kind": "sufficiency", "pattern": {"rosemary": 1}, "effect": "+D", "not": True}, POTIONS)["status"] == "true"
    assert ask({"kind": "sufficiency", "pattern": {"chamomile": "any"}, "effect": "none"}, POTIONS)["status"] == "true"


def test_necessity_needs_a_witness_and_a_test():
    nettle = {"kind": "necessity", "effect": "+D", "pattern": {"nettle": "any"}}
    assert ask(nettle, POTIONS) == {"status": "true", "for": [5, 6], "against": [], "tested": 4}
    assert ask(nettle, POTIONS[4:])["status"] == "unknown"          # nothing without nettle was tried
    sweet = {"kind": "necessity", "effect": "sweet", "pattern": {"sage": "any", "chamomile": "any"}}
    assert ask(sweet, POTIONS)["against"] == [3]                    # dill + mint is sweet too
    either = {**sweet, "pattern": [{"sage": "any", "chamomile": "any"}, {"dill": "any", "mint": "any"}]}
    assert ask(either, POTIONS)["status"] == "true"


# --- relations --------------------------------------------------------------------------------


def test_relation_counts_only_pairs_differing_in_one_plant():
    potions = brewed(
        {"elderberry": 1, "sage": 1, "dill": 1},   # 1 +I 2
        {"elderberry": 2, "sage": 1, "dill": 1},   # 2 +I 5
        {"elderberry": 4, "sage": 1, "dill": 1},   # 3 +I 20
        {"elderberry": 5, "sage": 1, "dill": 1},   # 4 +I 20 (capped)
        {"elderberry": 3, "sage": 1, "dill": 2},   # 5 differs in dill too: confounded with the others
    )
    answer = ask({"kind": "relation", "plant": "elderberry", "effect": "+I", "direction": "increases"}, potions)
    assert answer["status"] == "true" and answer["flat"] == [[3, 4]] and answer["tested"] == 6
    assert answer["confounded"] == 4
    assert ask({"kind": "relation", "plant": "elderberry", "effect": "+I", "direction": "decreases"}, potions)["status"] == "false"
    assert ask({"kind": "relation", "plant": "mint", "effect": "+I", "direction": "increases"}, potions)["status"] == "unknown"


def test_adding_a_plant_is_a_relation_from_zero():
    potions = brewed({"mint": 2, "chamomile": 4, "rosemary": 2}, {"mint": 2, "chamomile": 4, "rosemary": 2, "basil": 1})
    assert ask({"kind": "relation", "plant": "basil", "effect": "+S", "direction": "increases"}, potions)["for"] == [[1, 2]]


def test_a_parity_rule_breaks_a_relation():
    potions = brewed({"elderberry": 2, "sage": 1, "dill": 1}, {"elderberry": 2, "sage": 2, "dill": 1})   # +I 5, then none
    answer = ask({"kind": "relation", "plant": "sage", "effect": "+I", "direction": "increases"}, potions)
    assert answer["status"] == "false" and answer["against"] == [[1, 2]]


# --- soils ------------------------------------------------------------------------------------


def plantings(plant, soil, survived):
    return [Finished(i, plant, soil, 1, 3, s) for i, s in enumerate(survived, start=1)]


def test_soil_claims():
    dead = plantings("nettle", "black", [False, False])
    assert ask({"kind": "soil", "plant": "nettle", "soil": "black", "claim": "always_dies"}, history=dead)["status"] == "true"
    assert ask({"kind": "soil", "plant": "nettle", "soil": "black", "claim": "always_survives"}, history=dead)["status"] == "false"
    assert ask({"kind": "soil", "plant": "nettle", "soil": "yellow", "claim": "always_dies"}, history=dead)["status"] == "unknown"
    timed = ask({"kind": "soil", "plant": "nettle", "soil": "black", "claim": "growth_time", "turns": 2}, history=dead)
    assert timed["status"] == "true" and timed["times"] == [2]


def test_survival_rate_uses_the_95_percent_interval():
    few = plantings("dill", "brown", [True, True, True, False])
    answer = ask({"kind": "soil", "plant": "dill", "soil": "brown", "claim": "survival_at_least", "rate": 50}, history=few)
    assert answer["status"] == "unknown" and answer["grew"] == 3 and answer["died"] == 1
    many = plantings("dill", "brown", [True] * 30 + [False] * 10)
    assert ask({"kind": "soil", "plant": "dill", "soil": "brown", "claim": "survival_at_least", "rate": 50}, history=many)["status"] == "true"
    assert ask({"kind": "soil", "plant": "dill", "soil": "brown", "claim": "survival_at_most", "rate": 50}, history=many)["status"] == "false"
    low, high = wilson(30, 40)
    assert 0.59 < low < 0.61 and 0.85 < high < 0.87


@pytest.mark.parametrize(
    "statement, message",
    [
        ({"kind": "guess"}, '"kind" must be one of'),
        ({"kind": "sufficiency", "effect": "sweet"}, 'needs a "pattern"'),
        ({"kind": "sufficiency", "pattern": {"sage": 1}, "effect": "salty"}, '"effect" must be'),
        ({"kind": "sufficiency", "pattern": {"sage": 1}, "effect": "sweet", "at_least": 5}, '"at_least" needs a stat'),
        ({"kind": "relation", "plant": "sage", "effect": "sweet", "direction": "increases"}, "a stat with its sign"),
        ({"kind": "relation", "plant": "sage", "effect": "+I", "direction": "up"}, '"direction"'),
        ({"kind": "soil", "plant": "dill", "soil": "brown", "claim": "survival_at_least"}, '"rate"'),
        ({"kind": "soil", "plant": "dill", "soil": "red", "claim": "always_dies"}, '"soil"'),
    ],
)
def test_malformed_statements(statement, message):
    with pytest.raises(ValueError, match=message):
        ask(statement)
