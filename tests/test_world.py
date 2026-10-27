import pytest

from environment.brewer import RecipeError
from environment.goals import Allergy, Goal, GoalKind, score_goal, validate_allergy
from environment.knowledge_base import LogError
from environment.world import InfeasibleBrew, World

STRENGTH_10 = Goal(GoalKind.TARGET, "S", target=10)
INTEL_5_TURNS = Goal(GoalKind.TIME, "I", turns=5)
P5_P3 = Allergy(frozenset({"p5", "p3"}))


def make_world(goals=(STRENGTH_10,), allergy=None, turn_cap=100, seed=0) -> World:
    return World.create(7, (2, 6), list(goals), allergy, turn_cap, seed)


def advance(world: World, turns: int) -> None:
    for _ in range(turns):
        world.skip()
        world.end_turn()


# --- goals and allergy ------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(kind=GoalKind.TIME, stat="X", turns=5),
        dict(kind=GoalKind.TIME, stat="S"),
        dict(kind=GoalKind.TIME, stat="S", turns=5, target=10),
        dict(kind=GoalKind.TARGET, stat="S"),
        dict(kind=GoalKind.TARGET, stat="S", target=10, turns=5),
    ],
)
def test_invalid_goals(kwargs):
    with pytest.raises(ValueError):
        Goal(**kwargs)


def test_allergy_must_not_block_a_goal():
    with pytest.raises(ValueError):
        validate_allergy(Allergy(frozenset({"p1", "p5"})), [STRENGTH_10])
    validate_allergy(P5_P3, [STRENGTH_10])  # one required + one non-required is fine


def test_allergy_needs_two_known_plants():
    with pytest.raises(ValueError):
        Allergy(frozenset({"p1"}))
    with pytest.raises(ValueError):
        Allergy(frozenset({"p1", "p9"}))


# --- world creation and actions ---------------------------------------------


def test_create_is_reproducible():
    a, b = make_world(seed=3), make_world(seed=3)
    assert a.garden.growth_times == b.garden.growth_times
    assert all(2 <= g <= 6 for g in a.garden.growth_times.values())


def test_plant_gather_brew_cycle():
    world = make_world()
    g = world.garden.growth_times
    world.plant({1: "p1", 2: "p1", 3: "p5", 4: "p8", 5: "p8"})
    world.end_turn()
    advance(world, max(g["p1"], g["p5"], g["p8"]))
    gathered = world.gather()
    assert gathered.counts == {"p1": 2, "p5": 1, "p8": 2}
    potion = world.brew({"p1": 2, "p5": 1, "p8": 2})
    assert potion.id == 1 and potion.effect.positive == {"S": 2}
    assert dict(world.inventory.plants) == {}


def test_gather_clears_logged_plantings():
    world = make_world()
    world.plant({1: "p4"})
    world.log(garden=True, potions={})
    assert world.kb.plantings() == {1: "p4"}
    world.end_turn()
    advance(world, world.garden.growth_times["p4"])
    world.gather()
    assert world.kb.plantings() == {}


def test_failed_brews_change_nothing():
    world = make_world()
    world.inventory.add_plants({"p1": 2, "p5": 1})
    with pytest.raises(InfeasibleBrew) as err:
        world.brew({"p1": 2, "p5": 1, "p8": 2})
    assert err.value.shortages == {"p8": (2, 0)}
    with pytest.raises(RecipeError):
        world.brew({"p1": 2, "p5": 1})
    assert dict(world.inventory.plants) == {"p1": 2, "p5": 1}
    assert world.inventory.potions == []


# --- logging potions ----------------------------------------------------------


def test_log_potions_defaults_and_duplicates():
    world = make_world()
    world.inventory.add_plants({"p2": 3, "p4": 2, "p6": 2})
    world.brew({"p2": 1, "p4": 1, "p6": 1})
    world.brew({"p2": 2, "p4": 1, "p6": 1})
    result = world.log(garden=False, potions={1: {}, 2: {"p2": "higher"}})
    assert [log.outcome.render() for log in result.potions] == [
        "p2, p4, p6 → +I",
        "(higher) p2, p4, p6 → +I",
    ]
    assert all(log.new for log in result.potions)
    assert all(p.logged for p in world.inventory.potions)
    again = world.log(garden=False, potions={2: {"p2": "higher"}})
    assert not again.potions[0].new


@pytest.mark.parametrize(
    "potions, message",
    [
        ({5: {}}, "Unknown potion #5"),
        ({1: {"p7": "odd"}}, "does not contain p7"),
        ({1: {"p2": "big"}}, 'Invalid label "big"'),
    ],
)
def test_invalid_potion_logs_write_nothing(potions, message):
    world = make_world()
    world.inventory.add_plants({"p2": 1, "p4": 1, "p6": 1})
    world.brew({"p2": 1, "p4": 1, "p6": 1})
    world.plant({1: "p4"})
    with pytest.raises(LogError, match=message):
        world.log(garden=True, potions=potions)
    assert world.kb.outcomes() == [] and world.kb.plantings() == {}


# --- goals over time ----------------------------------------------------------


def test_target_goal_ends_when_reached_and_next_goal_starts():
    world = make_world(goals=[STRENGTH_10, INTEL_5_TURNS])
    world.inventory.add_plants({"p1": 4, "p5": 5, "p8": 4})
    advance(world, 2)                                  # turns 1–2
    world.brew({"p1": 2, "p5": 2, "p8": 2})            # turn 3: +S 5%, not enough
    assert world.end_turn().finished is None
    world.brew({"p1": 2, "p5": 3, "p8": 2})            # turn 4: +S 10%
    end = world.end_turn()
    assert end.finished.success and end.finished.best_intensity == 10
    assert end.finished.turns_used == 4 and end.finished.best_potion == 2
    assert end.next_goal == INTEL_5_TURNS and world.goal_start == 5


def test_allergic_potion_does_not_reach_target():
    world = make_world(allergy=P5_P3)
    world.inventory.add_plants({"p1": 2, "p5": 3, "p8": 2, "p3": 1})
    world.brew({"p1": 2, "p5": 3, "p8": 2, "p3": 1})   # +S 10%, but allergic
    assert world.end_turn().finished is None
    result = score_goal(STRENGTH_10, world.inventory.potions, P5_P3, 1, 1)
    assert result.allergy_violations == 1 and not result.success


def test_time_goal_ends_at_deadline_with_best_potion():
    world = make_world(goals=[INTEL_5_TURNS])
    world.inventory.add_plants({"p2": 6, "p4": 2, "p6": 2})
    world.brew({"p2": 2, "p4": 1, "p6": 1})            # turn 1: +I 5%
    world.end_turn()
    world.brew({"p2": 1, "p4": 1, "p6": 1})            # turn 2: +I 2%
    world.end_turn()
    advance(world, 2)                                  # turns 3–4
    world.skip()                                       # turn 5: deadline
    end = world.end_turn()
    assert end.finished.best_potion == 1 and end.finished.best_intensity == 5
    assert end.finished.turns_used == 5 and end.episode_over


def test_turn_cap_fails_open_target_goal():
    world = make_world(goals=[STRENGTH_10, INTEL_5_TURNS], turn_cap=3)
    advance(world, 2)
    world.skip()
    end = world.end_turn()
    assert end.episode_over and not end.finished.success
    assert len(world.results) == 1                     # the second goal never started
