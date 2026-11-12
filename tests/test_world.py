import pytest

from environment.brewer import RecipeError, effect_of
from environment.knowledge_base import LogError
from environment.requests import Request
from environment.world import DeliveryError, InfeasibleBrew, MixError, World

STRENGTH_10 = Request("s10", "text", "S", threshold=10)
WEEK_S25_NO_NETTLE = Request("s25", "text", "S", threshold=25, deadline_day=7, excluded=frozenset({"nettle"}))


def make_world(request=STRENGTH_10, turn_cap=100, seed=0) -> World:
    return World.create(7, request, turn_cap, seed)


def advance(world: World, turns: int) -> None:
    for _ in range(turns):
        world.skip()
        world.end_turn()


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


# --- delivery and the end of the episode -------------------------------------------


def test_delivery_ends_the_episode_and_uses_the_potion():
    world = make_world()
    world.inventory.add_plants({"mint": 2, "chamomile": 3, "rosemary": 2})
    advance(world, 2)
    world.brew({"mint": 2, "chamomile": 3, "rosemary": 2})            # turn 3: +S 10%
    world.end_turn()
    result = world.deliver(1)                                         # turn 4
    assert result.success and result.potion == 1 and result.turn == 4 and result.intensity == 10
    assert world.episode_over and world.inventory.potions[0].used


@pytest.mark.parametrize("pid, message", [(9, "Unknown potion #9."), (1, "Potion #1 was already used up.")])
def test_invalid_deliveries_change_nothing(pid, message):
    world = make_world()
    world.inventory.add_plants({"mint": 4, "sage": 2})
    world.brew_all([{"mint": 1, "sage": 1}, {"mint": 1, "sage": 1}])
    world.mix_all([[1, 2]])                                           # potions 1 and 2 used up
    with pytest.raises(DeliveryError, match=message):
        world.deliver(pid)
    assert world.result is None and not world.episode_over


def test_a_failed_delivery_also_ends_the_episode():
    world = make_world()
    world.inventory.add_plants({"mint": 2, "chamomile": 2, "rosemary": 2})
    world.brew({"mint": 2, "chamomile": 2, "rosemary": 2})            # +S 5%
    result = world.deliver(1)
    assert not result.success and result.failures == ("S 5% is below 10%",) and world.episode_over


def test_the_deadline_ends_the_episode_without_a_delivery():
    world = make_world(WEEK_S25_NO_NETTLE)
    assert world.last_turn == 70
    advance(world, 69)
    assert not world.episode_over and world.turn == 70
    advance(world, 1)
    assert world.episode_over and world.result.failures == ("nothing delivered",) and world.result.turn == 70


def test_delivery_on_the_last_turn_counts():
    world = make_world(WEEK_S25_NO_NETTLE)
    world.inventory.add_plants({"mint": 2, "chamomile": 4, "rosemary": 2, "basil": 1})
    advance(world, 68)
    world.brew({"mint": 2, "chamomile": 4, "rosemary": 2, "basil": 1})   # turn 69: S 20 + fragrant = 25
    world.end_turn()
    assert world.deliver(1).success and world.result.turn == 70


def test_the_turn_cap_ends_the_episode_before_a_later_deadline():
    world = make_world(WEEK_S25_NO_NETTLE, turn_cap=12)
    assert world.last_turn == 12
    advance(world, 12)
    assert world.episode_over and world.result.turn == 12


def test_result_survives_a_checkpoint():
    world = make_world()
    world.inventory.add_plants({"mint": 2, "sage": 1})
    world.brew({"mint": 2, "sage": 1})
    world.deliver(1)
    copy = World.from_dict(world.to_dict())
    assert copy.result == world.result and copy.request == world.request


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


def test_a_mixed_potion_can_meet_the_request():
    world = make_world(Request("s30", "text", "S", threshold=30))
    world.inventory.add_plants({"mint": 2, "chamomile": 5, "rosemary": 2, "nettle": 1})
    world.brew_all([{"mint": 2, "chamomile": 4, "rosemary": 2}, {"chamomile": 1, "nettle": 1}])   # S 20; warming
    world.end_turn()
    (mixed,) = world.mix_all([[1, 2]])
    assert mixed.effect.positive == {"S": 30}
    world.end_turn()
    assert world.deliver(3).success


def test_an_excluded_plant_anywhere_in_a_mix_fails():
    world = make_world(WEEK_S25_NO_NETTLE)
    world.inventory.add_plants({"mint": 2, "chamomile": 5, "rosemary": 2, "nettle": 1})
    world.brew_all([{"mint": 2, "chamomile": 4, "rosemary": 2}, {"chamomile": 1, "nettle": 1}])
    world.mix_all([[1, 2]])                                               # S 30, but contains nettle
    assert world.deliver(3).failures == ("contains nettle",)


def test_mixed_potions_survive_a_checkpoint():
    world = make_world()
    brew_spec_pair(world)
    world.mix_all([[2, 1]])
    copy = World.from_dict(world.to_dict())
    assert copy.inventory.potions == world.inventory.potions
    assert copy.inventory.potions[2].origin == (2, 1)
