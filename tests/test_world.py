import pytest

from environment.brewer import RecipeError, effect_of
from environment.goals import Allergy, Goal, GoalKind, score_goal, validate_allergy
from environment.knowledge_base import LogError
from environment.world import InfeasibleBrew, MixError, World

STRENGTH_10 = Goal(GoalKind.TARGET, "S", target=10)
INTEL_5_TURNS = Goal(GoalKind.TIME, "I", turns=5)
P5_P3 = Allergy(frozenset({"chamomile", "nettle"}))


def make_world(goals=(STRENGTH_10,), allergy=None, turn_cap=100, seed=0) -> World:
    return World.create(7, list(goals), allergy, turn_cap, seed)


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
        validate_allergy(Allergy(frozenset({"mint", "chamomile"})), [STRENGTH_10])
    validate_allergy(P5_P3, [STRENGTH_10])  # one required + one non-required is fine


def test_allergy_needs_two_known_plants():
    with pytest.raises(ValueError):
        Allergy(frozenset({"mint"}))
    with pytest.raises(ValueError):
        Allergy(frozenset({"mint", "lavender"}))


# --- world creation and actions ---------------------------------------------


def test_same_seed_same_survival_rolls():
    a, b = make_world(seed=3), make_world(seed=3)
    for world in (a, b):
        world.plant({p: ("dill", "brown") for p in range(1, 8)})   # 75% survival, 2 turns
        world.end_turn()
        advance(world, 1)
    assert a.garden.history == b.garden.history and len(a.garden.history) == 7


def test_plant_gather_brew_cycle():
    world = make_world()
    world.plant({1: ("mint", "brown"), 2: ("mint", "brown"), 3: ("chamomile", "yellow"),
                 4: ("rosemary", "black"), 5: ("rosemary", "black")})   # ready after 2, 3 and 4 turns
    world.end_turn()
    advance(world, 3)
    gathered = world.gather()
    assert gathered.counts == {"mint": 2, "chamomile": 1, "rosemary": 2}
    potion = world.brew({"mint": 2, "chamomile": 1, "rosemary": 2})
    assert potion.id == 1 and potion.effect.positive == {"S": 2}
    assert dict(world.inventory.plants) == {}


def test_a_death_is_recorded_and_gather_clears_it():
    world = make_world()
    world.plant({1: ("elderberry", "brown"), 2: ("elderberry", "black")})   # brown: dies after 2
    world.end_turn()
    advance(world, 1)
    assert world.turn == 3 and world.view().died[0].plot == 1 and 1 not in world.view().free
    assert world.growth_records()[("elderberry", "brown")].died == 1
    result = world.gather()
    assert result.counts == {} and result.cleared == [1] and not world.inventory.plants


def test_failed_brews_change_nothing():
    world = make_world()
    world.inventory.add_plants({"mint": 2, "chamomile": 1})
    with pytest.raises(InfeasibleBrew) as err:
        world.brew({"mint": 2, "chamomile": 1, "rosemary": 2})
    assert err.value.shortages == {"rosemary": (2, 0)}
    with pytest.raises(RecipeError):
        world.brew({"mint": 2})
    assert dict(world.inventory.plants) == {"mint": 2, "chamomile": 1}
    assert world.inventory.potions == []


# --- logging potions ----------------------------------------------------------


def test_log_potions_defaults_and_duplicates():
    world = make_world()
    world.inventory.add_plants({"elderberry": 3, "sage": 2, "dill": 2})
    world.brew({"elderberry": 1, "sage": 1, "dill": 1})
    world.brew({"elderberry": 2, "sage": 1, "dill": 1})
    result = world.log({1: {}, 2: {"elderberry": "higher"}})
    assert [log.outcome.render() for log in result] == [
        "dill, elderberry, sage → +I",
        "dill, (higher) elderberry, sage → +I",
    ]
    assert all(log.new for log in result)
    assert all(p.logged for p in world.inventory.potions)
    again = world.log({2: {"elderberry": "higher"}})
    assert not again[0].new


@pytest.mark.parametrize(
    "potions, message",
    [
        ({5: {}}, "Unknown potion #5"),
        ({1: {"basil": "odd"}}, "does not contain basil"),
        ({1: {"elderberry": "big"}}, 'Invalid label "big"'),
    ],
)
def test_invalid_potion_logs_write_nothing(potions, message):
    world = make_world()
    world.inventory.add_plants({"elderberry": 1, "sage": 1, "dill": 1})
    world.brew({"elderberry": 1, "sage": 1, "dill": 1})
    with pytest.raises(LogError, match=message):
        world.log(potions)
    assert world.kb.outcomes() == []


# --- goals over time ----------------------------------------------------------


def test_target_goal_ends_when_reached_and_next_goal_starts():
    world = make_world(goals=[STRENGTH_10, INTEL_5_TURNS])
    world.inventory.add_plants({"mint": 4, "chamomile": 5, "rosemary": 4})
    advance(world, 2)                                  # turns 1–2
    world.brew({"mint": 2, "chamomile": 2, "rosemary": 2})            # turn 3: +S 5%, not enough
    assert world.end_turn().finished is None
    world.brew({"mint": 2, "chamomile": 3, "rosemary": 2})            # turn 4: +S 10%
    end = world.end_turn()
    assert end.finished.success and end.finished.best_intensity == 10
    assert end.finished.turns_used == 4 and end.finished.best_potion == 2
    assert end.next_goal == INTEL_5_TURNS and world.goal_start == 5


def test_allergic_potion_does_not_reach_target():
    world = make_world(allergy=P5_P3)
    world.inventory.add_plants({"mint": 2, "chamomile": 3, "rosemary": 2, "nettle": 1})
    world.brew({"mint": 2, "chamomile": 3, "rosemary": 2, "nettle": 1})   # +S 10%, but allergic
    assert world.end_turn().finished is None
    result = score_goal(STRENGTH_10, world.inventory.potions, P5_P3, 1, 1)
    assert result.allergy_violations == 1 and not result.success


def test_time_goal_ends_at_deadline_with_best_potion():
    world = make_world(goals=[INTEL_5_TURNS])
    world.inventory.add_plants({"elderberry": 6, "sage": 2, "dill": 2})
    world.brew({"elderberry": 2, "sage": 1, "dill": 1})            # turn 1: +I 5%
    world.end_turn()
    world.brew({"elderberry": 1, "sage": 1, "dill": 1})            # turn 2: +I 2%
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


# --- mixing ---------------------------------------------------------------------


def brew_spec_pair(world: World):
    world.inventory.add_plants({"sage": 1, "chamomile": 1, "nettle": 2, "mint": 1, "elderberry": 1})
    return world.brew_all([{"sage": 1, "chamomile": 1, "nettle": 1}, {"nettle": 1, "mint": 1, "elderberry": 1}])


def test_mix_sums_the_recipes_and_uses_up_the_inputs():
    world = make_world()
    brew_spec_pair(world)
    (mixed,) = world.mix_all([[1, 2]])
    assert mixed.id == 3 and mixed.origin == (1, 2) and mixed.turn == world.turn
    assert mixed.recipe == {"sage": 1, "chamomile": 1, "nettle": 2, "mint": 1, "elderberry": 1}   # spec example
    assert mixed.effect == effect_of(mixed.recipe)
    assert [p.used for p in world.inventory.potions] == [True, True, False]
    assert [p.id for p in world.inventory.held] == [3]


@pytest.mark.parametrize(
    "mixes, message",
    [
        ([], "Give at least one mix."),
        ([[1]], "A mix needs at least 2 potions."),
        ([[1, 9]], "Unknown potion #9."),
        ([[1, 1]], "Potion #1 appears more than once."),
        ([[1, 2], [2, 1]], "Mix 2: Potion #2 appears more than once."),
    ],
)
def test_invalid_mixes_change_nothing(mixes, message):
    world = make_world()
    brew_spec_pair(world)
    with pytest.raises(MixError, match=message):
        world.mix_all(mixes)
    assert len(world.inventory.potions) == 2 and not any(p.used for p in world.inventory.potions)


def test_used_potion_cannot_be_mixed_again():
    world = make_world()
    brew_spec_pair(world)
    world.inventory.add_plants({"mint": 1, "sage": 1})
    world.brew({"mint": 1, "sage": 1})
    world.mix_all([[1, 2]])
    with pytest.raises(MixError, match="Potion #1 was already used up."):
        world.mix_all([[1, 3]])


def test_mix_reaches_a_target():
    world = make_world(goals=(Goal(GoalKind.TARGET, "S", target=30),))
    world.inventory.add_plants({"mint": 2, "chamomile": 5, "rosemary": 2, "nettle": 1})
    world.brew_all([{"mint": 2, "chamomile": 4, "rosemary": 2}, {"chamomile": 1, "nettle": 1}])   # S 20; warming
    world.end_turn()
    assert not world.results
    (mixed,) = world.mix_all([[1, 2]])
    assert mixed.effect.positive == {"S": 30}
    world.end_turn()
    assert world.results[0].success and world.results[0].best_potion == 3


def test_used_potions_are_not_scored():
    world = make_world(goals=(Goal(GoalKind.TIME, "S", turns=5),))
    world.inventory.add_plants({"mint": 2, "chamomile": 4, "rosemary": 2, "elderberry": 1, "dill": 1})
    world.brew_all([{"mint": 2, "chamomile": 4, "rosemary": 2}, {"elderberry": 1, "dill": 1}])
    world.mix_all([[1, 2]])   # adds elderberry + mint (bitter), dill + rosemary (bitter), dill + mint (sweet): cancel
    result = score_goal(world.goals[0], world.inventory.potions, None, 1, world.turn)
    assert result.best_potion == 3


def test_mixed_potions_survive_a_checkpoint():
    world = make_world()
    brew_spec_pair(world)
    world.mix_all([[2, 1]])
    copy = World.from_dict(world.to_dict())
    assert copy.inventory.potions == world.inventory.potions
    assert copy.inventory.potions[2].origin == (2, 1)
