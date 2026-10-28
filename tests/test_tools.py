import pytest

from environment.brewer import PLANTS
from environment.goals import Goal, GoalKind
from environment.lore import LORE
from environment.world import World
from tools.dispatcher import Dispatcher
from tools.observation import turn_header

GROWTH = {"mint": 3, "elderberry": 4, "nettle": 3, "sage": 2, "chamomile": 3, "dill": 3, "basil": 6, "rosemary": 3}


@pytest.fixture
def world() -> World:
    w = World.create(7, (2, 6), [Goal(GoalKind.TARGET, "S", target=20)], None, 100, seed=0)
    w.garden.growth_times = dict(GROWTH)
    assert set(w.garden.growth_times) == set(PLANTS)
    return w


def act(d: Dispatcher, call) -> str:
    """Run one action and end the turn if it cost one."""
    result = d.handle(call)
    if result.ends_turn:
        d.world.end_turn()
    return result.text


def test_spec_garden_example_as_the_agent_sees_it(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"2": "elderberry", "4": "sage"}})   # turn 1
    act(d, {"action": "skip"})                                     # turn 2
    act(d, {"action": "plant", "plots": {"5": "chamomile", "7": "basil"}})   # turn 3
    act(d, {"action": "skip"})                                     # turn 4
    assert turn_header(world) == (
        "[Turn 5]\n"
        "Garden: free: 1, 3, 6; growing: 5, 7; ready: 2 (waiting 0), 4 (waiting 2)\n"
        "Choose your action."
    )
    assert act(d, {"action": "log", "garden": True}) == (
        "Logged: growth elderberry = 4 turns, sage = 2 turns; "
        "plantings: plot 2 (elderberry), plot 4 (sage), plot 5 (chamomile), plot 7 (basil)."
    )
    assert turn_header(world).splitlines()[1] == (
        "Garden: free: 1, 3, 6; growing: 7 (basil); "
        "ready: 2 (elderberry, waiting 1), 4 (sage, waiting 3), 5 (chamomile, waiting 0)"
    )


def test_turns_left_shown_when_known(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"1": "basil"}})    # turn 1: ready at 7
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    act(d, {"action": "plant", "plots": {"2": "basil"}})    # turn 4: ready at 10
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    act(d, {"action": "log", "garden": True})            # turn 7: basil growth + both plantings
    assert "growing: 2 (basil, 2 turns left)" in turn_header(world)
    act(d, {"action": "skip"})                           # turn 8
    assert "growing: 2 (basil, 1 turn left)" in turn_header(world)


def test_plant_partial_success(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"5": "elderberry"}})
    text = act(d, {"action": "plant", "plots": {"3": "elderberry", "5": "sage", "12": "elderberry", "6": "lavender"}})
    assert text == (
        "Planted: plot 3 (elderberry). "
        "Failed: plot 5 (occupied), plot 12 (does not exist), plot 6 (unknown plant lavender)."
    )


def test_gather_texts(world):
    d = Dispatcher(world)
    assert act(d, {"tool": "gather"}) == "Gathered nothing."
    act(d, {"action": "plant", "plots": {"1": "sage", "2": "sage", "3": "elderberry"}})
    for _ in range(4):
        act(d, {"action": "skip"})
    assert act(d, {"tool": "gather"}) == "Gathered: +1 elderberry, +2 sage. Plots now free: 1, 2, 3."


def test_gather_is_free_and_growth_stays_loggable_that_turn(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"1": "sage", "2": "elderberry"}})   # turn 1: sage ready at 3
    act(d, {"action": "skip"})                                                # turn 2
    assert world.turn == 3
    assert act(d, {"tool": "gather"}) == "Gathered: +1 sage. Plots now free: 1."
    assert world.turn == 3                                                    # no turn spent
    assert act(d, {"action": "log", "garden": True}) == (
        "Logged: growth sage = 2 turns; plantings: plot 2 (elderberry)."    # gathered sage still counts
    )
    act(d, {"tool": "gather"})                                                # turn 4: nothing ready
    assert act(d, {"action": "log", "garden": True}) == "Logged: nothing new."


def test_gather_then_replant_in_one_turn(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"1": "sage"}})
    act(d, {"action": "skip"})
    act(d, {"tool": "gather"})
    assert act(d, {"action": "plant", "plots": {"1": "mint"}}) == "Planted: plot 1 (mint)."


def test_brew_several_potions_in_one_turn(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"elderberry": 3, "sage": 2, "dill": 2, "mint": 1})
    text = act(d, {"action": "brew", "recipes": [
        {"elderberry": 1, "sage": 1, "dill": 1},
        {"elderberry": 2, "sage": 1, "dill": 1, "mint": 1},
    ]})
    assert text == (
        'Brewed {"elderberry": 1, "sage": 1, "dill": 1} → {"positive": {"I": 2}, "negative": {}} (potion #1)\n'
        'Brewed {"elderberry": 2, "sage": 1, "dill": 1, "mint": 1} → {"positive": {"I": 5}, "negative": {}} (potion #2)'
    )
    assert world.turn == 2 and not world.inventory.plants   # one turn, everything used


def test_multi_brew_is_all_or_nothing(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"elderberry": 2, "sage": 2, "dill": 2})
    two = [{"elderberry": 1, "sage": 1, "dill": 1}, {"elderberry": 2, "sage": 1, "dill": 1}]
    failed = d.handle({"action": "brew", "recipes": two})
    assert failed.error and not failed.ends_turn
    assert failed.text == "Not enough plants for these recipes together: need 3 elderberry, have 2. Nothing was brewed."
    bad = d.handle({"action": "brew", "recipes": [two[0], {"elderberry": 1}]})
    assert bad.text == "Recipe 2: A recipe needs 3–4 distinct plants."
    assert dict(world.inventory.plants) == {"elderberry": 2, "sage": 2, "dill": 2} and not world.inventory.potions
    assert d.handle({"action": "brew", "recipe": two[0], "recipes": two}).text.startswith('Give either "recipe"')


def test_multi_brew_reaches_a_target(world):
    world.goals[0] = Goal(GoalKind.TARGET, "I", target=5)
    d = Dispatcher(world)
    world.inventory.add_plants({"elderberry": 3, "sage": 2, "dill": 2})
    act(d, {"action": "brew", "recipes": [{"elderberry": 1, "sage": 1, "dill": 1}, {"elderberry": 2, "sage": 1, "dill": 1}]})
    assert world.results and world.results[0].success and world.results[0].best_intensity == 5


def test_brew_texts(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"mint": 2, "chamomile": 4, "rosemary": 2})
    assert act(d, {"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}}) == (
        'Brewed {"mint": 2, "chamomile": 4, "rosemary": 2} → {"positive": {"S": 20}, "negative": {}} (potion #1)'
    )
    failed = d.handle({"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}})
    assert failed.error and not failed.ends_turn
    assert failed.text == (
        "Not enough plants: need 2 mint, have 0; need 4 chamomile, have 0; need 2 rosemary, have 0. Nothing was brewed."
    )
    assert d.handle({"action": "brew", "recipe": {"mint": 1}}).text == "A recipe needs 3–4 distinct plants."


def test_log_potions_and_lookup(world):
    world.lore = False  # lore has its own test
    d = Dispatcher(world)
    world.inventory.add_plants({"mint": 1, "elderberry": 4, "sage": 3, "dill": 3})
    act(d, {"action": "brew", "recipe": {"mint": 1, "elderberry": 1, "dill": 1}})
    act(d, {"action": "brew", "recipe": {"elderberry": 1, "sage": 1, "dill": 1}})
    act(d, {"action": "brew", "recipe": {"elderberry": 2, "sage": 1, "dill": 1}})
    text = act(d, {"action": "log", "potions": [{"id": 1}, {"id": 2}, {"id": 3, "labels": {"elderberry": "higher"}}]})
    assert text == (
        "Logged: potion #1: dill, elderberry, mint → none; potion #2: dill, elderberry, sage → +I; "
        "potion #3: dill, (higher) elderberry, sage → +I."
    )
    assert act(d, {"action": "log", "potions": [{"id": 3, "labels": {"elderberry": "higher"}}]}) == (
        "Logged: potion #3: already known."
    )
    lookup = d.handle({"tool": "kb_lookup", "plants": ["sage", "rosemary"]})
    assert not lookup.ends_turn
    assert lookup.text == (
        "sage: growth time unknown. Interactions: dill, elderberry, sage → +I; dill, (higher) elderberry, sage → +I.\n"
        "rosemary: growth time unknown. Interactions: none."
    )
    assert d.handle({"tool": "inventory"}).text == (
        "plants: sage: 1; potions: #1 (logged), #2 (logged), #3 (logged)"
    )


def test_logging_unlocks_lore_read_with_lookup(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"mint": 1, "elderberry": 2, "sage": 1, "dill": 2})
    act(d, {"action": "brew", "recipes": [{"mint": 1, "elderberry": 1, "dill": 1}, {"elderberry": 1, "sage": 1, "dill": 1}]})
    assert d.handle({"tool": "kb_lookup", "plants": ["dill"]}).text.endswith("Lore: none yet.")
    text = act(d, {"action": "log", "potions": [{"id": 1}]})
    assert text == ("Logged: potion #1: dill, elderberry, mint → none "
                    "(the old herbals hold new lore about its plants: read it with kb_lookup).")
    assert d.handle({"tool": "kb_lookup", "plants": ["dill"]}).text.endswith("Lore: " + LORE[("dill", "elderberry")])
    assert d.handle({"tool": "kb_lookup", "plants": ["mint"]}).text.endswith("Lore: none yet.")
    act(d, {"action": "log", "potions": [{"id": 2}]})                      # adds dill+sage, elderberry+sage
    assert world.kb.lore("sage") == [LORE[("dill", "sage")], LORE[("elderberry", "sage")]]
    assert act(d, {"action": "log", "potions": [{"id": 2}]}) == "Logged: potion #2: already known."   # nothing new


def test_no_lore_when_switched_off(world):
    world.lore = False
    d = Dispatcher(world)
    world.inventory.add_plants({"elderberry": 1, "sage": 1, "dill": 1})
    act(d, {"action": "brew", "recipe": {"elderberry": 1, "sage": 1, "dill": 1}})
    assert act(d, {"action": "log", "potions": [{"id": 1}]}) == "Logged: potion #1: dill, elderberry, sage → +I."
    assert "Lore" not in d.handle({"tool": "kb_lookup", "plants": ["sage"]}).text and world.kb.lore() == []


@pytest.mark.parametrize(
    "call, message",
    [
        ("{not json", "Malformed JSON."),
        ("[1, 2]", "A call must be a JSON object."),
        ({"action": "skip", "tool": "inventory"}, 'exactly one of "action" or "tool"'),
        ({"action": "dance"}, "Unknown action 'dance'"),
        ({"tool": "kb_lookup", "plants": ["lavender"]}, "Unknown plant lavender."),
        ({"action": "log"}, "Nothing to log"),
        ({"action": "log", "potions": [{"id": 4}]}, "Unknown potion #4."),
        ({"action": "plant", "plots": {"x": "mint"}}, "A plot number must be a whole number"),
    ],
)
def test_errors_cost_no_turn(world, call, message):
    d = Dispatcher(world)
    result = d.handle(call)
    assert result.error and not result.ends_turn
    assert message in result.text
    assert world.turn == 1


def test_three_failures_force_a_skip_and_counter_resets(world):
    d = Dispatcher(world)
    assert not d.handle("{bad").ends_turn
    assert not d.handle("{bad").ends_turn
    third = d.handle("{bad")
    assert third.ends_turn and third.text == "Malformed JSON. 3 failed attempts: the turn is skipped."
    world.end_turn()
    assert not d.handle("{bad").ends_turn   # new turn: counter starts again
