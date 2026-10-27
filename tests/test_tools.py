import pytest

from environment.brewer import PLANTS
from environment.goals import Goal, GoalKind
from environment.world import World
from tools.dispatcher import Dispatcher
from tools.observation import turn_header

GROWTH = {"p1": 3, "p2": 4, "p3": 3, "p4": 2, "p5": 3, "p6": 3, "p7": 6, "p8": 3}


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
    act(d, {"action": "plant", "plots": {"2": "p2", "4": "p4"}})   # turn 1
    act(d, {"action": "skip"})                                     # turn 2
    act(d, {"action": "plant", "plots": {"5": "p5", "7": "p7"}})   # turn 3
    act(d, {"action": "skip"})                                     # turn 4
    assert turn_header(world) == (
        "[Turn 5]\n"
        "Garden: free: 1, 3, 6; growing: 5, 7; ready: 2 (waiting 0), 4 (waiting 2)\n"
        "Choose your action."
    )
    assert act(d, {"action": "log", "garden": True}) == (
        "Logged: growth p2 = 4 turns, p4 = 2 turns; "
        "plantings: plot 2 (p2), plot 4 (p4), plot 5 (p5), plot 7 (p7)."
    )
    assert turn_header(world).splitlines()[1] == (
        "Garden: free: 1, 3, 6; growing: 7 (p7); "
        "ready: 2 (p2, waiting 1), 4 (p4, waiting 3), 5 (p5, waiting 0)"
    )


def test_turns_left_shown_when_known(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"1": "p7"}})    # turn 1: ready at 7
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    act(d, {"action": "plant", "plots": {"2": "p7"}})    # turn 4: ready at 10
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    act(d, {"action": "log", "garden": True})            # turn 7: p7 growth + both plantings
    assert "growing: 2 (p7, 2 turns left)" in turn_header(world)
    act(d, {"action": "skip"})                           # turn 8
    assert "growing: 2 (p7, 1 turn left)" in turn_header(world)


def test_plant_partial_success(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": {"5": "p2"}})
    text = act(d, {"action": "plant", "plots": {"3": "p2", "5": "p4", "12": "p2", "6": "p9"}})
    assert text == (
        "Planted: plot 3 (p2). "
        "Failed: plot 5 (occupied), plot 12 (does not exist), plot 6 (unknown plant p9)."
    )


def test_gather_texts(world):
    d = Dispatcher(world)
    assert act(d, {"action": "gather"}) == "Gathered nothing."
    act(d, {"action": "plant", "plots": {"1": "p4", "2": "p4", "3": "p2"}})
    for _ in range(4):
        act(d, {"action": "skip"})
    assert act(d, {"action": "gather"}) == "Gathered: +1 p2, +2 p4."


def test_brew_texts(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"p1": 2, "p5": 4, "p8": 2})
    assert act(d, {"action": "brew", "recipe": {"p1": 2, "p5": 4, "p8": 2}}) == (
        'Brewed {"p1": 2, "p5": 4, "p8": 2} → {"positive": {"S": 20}, "negative": {}} (potion #1)'
    )
    failed = d.handle({"action": "brew", "recipe": {"p1": 2, "p5": 4, "p8": 2}})
    assert failed.error and not failed.ends_turn
    assert failed.text == "Not enough plants: need 2 p1, have 0; need 4 p5, have 0; need 2 p8, have 0."
    assert d.handle({"action": "brew", "recipe": {"p1": 1}}).text == "A recipe needs 3–4 distinct plants."


def test_log_potions_and_lookup(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"p1": 1, "p2": 4, "p4": 3, "p6": 3})
    act(d, {"action": "brew", "recipe": {"p1": 1, "p2": 1, "p6": 1}})
    act(d, {"action": "brew", "recipe": {"p2": 1, "p4": 1, "p6": 1}})
    act(d, {"action": "brew", "recipe": {"p2": 2, "p4": 1, "p6": 1}})
    text = act(d, {"action": "log", "potions": [{"id": 1}, {"id": 2}, {"id": 3, "labels": {"p2": "higher"}}]})
    assert text == (
        "Logged: potion #1: p1, p2, p6 → none; potion #2: p2, p4, p6 → +I; "
        "potion #3: (higher) p2, p4, p6 → +I."
    )
    assert act(d, {"action": "log", "potions": [{"id": 3, "labels": {"p2": "higher"}}]}) == (
        "Logged: potion #3: already known."
    )
    lookup = d.handle({"tool": "kb_lookup", "plants": ["p4", "p8"]})
    assert not lookup.ends_turn
    assert lookup.text == (
        "p4: growth time unknown. Interactions: p2, p4, p6 → +I; (higher) p2, p4, p6 → +I.\n"
        "p8: growth time unknown. Interactions: none."
    )
    assert d.handle({"tool": "inventory"}).text == (
        "plants: p4: 1; potions: #1 (logged), #2 (logged), #3 (logged)"
    )


@pytest.mark.parametrize(
    "call, message",
    [
        ("{not json", "Malformed JSON."),
        ("[1, 2]", "A call must be a JSON object."),
        ({"action": "skip", "tool": "inventory"}, 'exactly one of "action" or "tool"'),
        ({"action": "dance"}, "Unknown action 'dance'"),
        ({"tool": "kb_lookup", "plants": ["p9"]}, "Unknown plant p9."),
        ({"action": "log"}, "Nothing to log"),
        ({"action": "log", "potions": [{"id": 4}]}, "Unknown potion #4."),
        ({"action": "plant", "plots": {"x": "p1"}}, "A plot number must be a whole number"),
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
