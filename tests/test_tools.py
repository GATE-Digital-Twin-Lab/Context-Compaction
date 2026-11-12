import pytest

from environment.requests import Request
from environment.lore import LORE
from environment.world import World
from tools.dispatcher import Dispatcher
from tools.observation import turn_header

@pytest.fixture
def world() -> World:
    return World.create(7, Request("s20", "text", "S", threshold=20), 100, seed=0)


def act(d: Dispatcher, call) -> str:
    """Run one action and end the turn if it cost one."""
    result = d.handle(call)
    if result.ends_turn:
        d.world.end_turn()
    return result.text


def plots(**spec: str) -> dict:
    """plots(p2="sage yellow") -> {"2": {"plant": "sage", "soil": "yellow"}}."""
    return {k[1:]: dict(zip(("plant", "soil"), v.split())) for k, v in spec.items()}


def test_spec_garden_line_as_the_agent_sees_it(world):
    """The garden line of demo_spec.md at day 3, turn 24."""
    d = Dispatcher(world)
    world.turn = 18
    act(d, {"action": "plant", "plots": plots(p5="basil black")})        # turn 18: dies at 24
    act(d, {"action": "plant", "plots": plots(p4="nettle yellow")})      # turn 19: ready at 24
    act(d, {"action": "skip"})                                           # turn 20
    act(d, {"action": "skip"})                                           # turn 21
    act(d, {"action": "plant", "plots": plots(p3="mint black")})         # turn 22: ready at 28
    act(d, {"action": "plant", "plots": plots(p2="sage yellow")})        # turn 23: ready at 25
    assert turn_header(world) == (
        "[Day 3, turn 24]\n"
        "Garden: free: 1, 6, 7; growing: 2 (sage, yellow, planted turn 23), 3 (mint, black, planted turn 22); "
        "ready: 4 (nettle, yellow, waiting 0); died: 5 (basil, black)\n"
        "Choose your action."
    )
    assert act(d, {"tool": "gather"}) == "Gathered: +1 nettle. Cleared dead plants: 5. Plots now free: 4, 5."
    assert "died" not in turn_header(world)


def test_turns_left_shown_once_the_pair_has_finished(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": plots(p1="basil brown")})    # turn 1: ready at 7
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    act(d, {"action": "plant", "plots": plots(p2="basil brown")})    # turn 4: ready at 10
    assert "growing: 1 (basil, brown, planted turn 1), 2 (basil, brown, planted turn 4)" in turn_header(world)
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    assert "growing: 2 (basil, brown, 3 turns left)" in turn_header(world)   # turn 7: plot 1 ready
    act(d, {"action": "skip"})
    act(d, {"action": "skip"})
    assert "growing: 2 (basil, brown, 1 turn left)" in turn_header(world)


def test_day_changes_every_ten_turns(world):
    assert turn_header(world).startswith("[Day 1, turn 1]")
    world.turn = 10
    assert turn_header(world).startswith("[Day 1, turn 10]")
    world.turn = 11
    assert turn_header(world).startswith("[Day 2, turn 11]")


def test_plant_partial_success(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": plots(p5="elderberry black")})
    text = act(d, {"action": "plant", "plots": plots(
        p3="elderberry black", p5="sage yellow", p12="elderberry black", p6="lavender black", p7="sage red")})
    assert text == (
        "Planted: plot 3 (elderberry, black). "
        "Failed: plot 5 (occupied), plot 12 (does not exist), plot 6 (unknown plant lavender), plot 7 (unknown soil red)."
    )


def test_plant_needs_a_soil(world):
    result = Dispatcher(world).handle({"action": "plant", "plots": {"1": "sage"}})
    assert result.error and result.text == 'Plot 1 needs a plant and a soil, e.g. {"plant": "sage", "soil": "yellow"}.'


def test_gather_texts(world):
    d = Dispatcher(world)
    assert act(d, {"tool": "gather"}) == "Gathered nothing."
    act(d, {"action": "plant", "plots": plots(p1="sage yellow", p2="sage yellow", p3="elderberry black")})
    for _ in range(5):
        act(d, {"action": "skip"})
    assert act(d, {"tool": "gather"}) == "Gathered: +1 elderberry, +2 sage. Plots now free: 1, 2, 3."


def test_gather_is_free_and_growth_is_recorded(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": plots(p1="sage yellow", p2="elderberry brown")})   # ready / dies at 3
    act(d, {"action": "skip"})
    assert world.turn == 3
    assert act(d, {"tool": "gather"}) == "Gathered: +1 sage. Cleared dead plants: 2. Plots now free: 1, 2."
    assert world.turn == 3                                                    # no turn spent
    assert d.handle({"tool": "kb_lookup", "plants": ["sage", "elderberry", "mint"]}).text.startswith(
        "Growth:\n"
        "- sage in yellow: 2 turns (planted 1, grew 1, died 0)\n"
        "- elderberry in brown: 2 turns (planted 1, grew 0, died 1)\n"
        "- mint: no planting finished yet\n"
    )


def test_gather_then_replant_in_one_turn(world):
    d = Dispatcher(world)
    act(d, {"action": "plant", "plots": plots(p1="sage yellow")})
    act(d, {"action": "skip"})
    act(d, {"tool": "gather"})
    assert act(d, {"action": "plant", "plots": plots(p1="mint brown")}) == "Planted: plot 1 (mint, brown)."


def test_brew_several_potions_in_one_turn(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"elderberry": 3, "sage": 2, "dill": 2, "mint": 1})
    text = act(d, {"action": "brew", "recipes": [
        {"elderberry": 1, "sage": 1, "dill": 1},
        {"elderberry": 2, "sage": 1, "dill": 1, "mint": 1},
    ]})
    assert text == (
        'Brewed {"elderberry": 1, "sage": 1, "dill": 1} → {"positive": {"I": 2}, "negative": {}, "secondary": []} (potion #1)\n'
        'Brewed {"elderberry": 2, "sage": 1, "dill": 1, "mint": 1} → {"positive": {"I": 5}, "negative": {}, "secondary": ["fragrant", "sweet", "bitter"]} (potion #2)'
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
    assert bad.text == "Recipe 2: A recipe needs 2–4 distinct plants."
    assert dict(world.inventory.plants) == {"elderberry": 2, "sage": 2, "dill": 2} and not world.inventory.potions
    assert d.handle({"action": "brew", "recipe": two[0], "recipes": two}).text.startswith('Give either "recipe"')


def test_deliver_texts(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"mint": 2, "chamomile": 4, "rosemary": 2})
    act(d, {"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}})   # +S 20%
    failed = d.handle({"action": "deliver", "potion": 5})
    assert failed.error and not failed.ends_turn and failed.text == "Unknown potion #5. Nothing was delivered."
    assert d.handle({"action": "deliver"}).text.startswith('"potion" must be a whole number')
    assert act(d, {"action": "deliver", "potion": 1}) == "Delivered potion #1. The request is closed."   # no verdict
    assert world.episode_over and world.result.success


def test_brew_texts(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"mint": 2, "chamomile": 4, "rosemary": 2})
    assert act(d, {"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}}) == (
        'Brewed {"mint": 2, "chamomile": 4, "rosemary": 2} → {"positive": {"S": 20}, "negative": {}, "secondary": []} (potion #1)'
    )
    failed = d.handle({"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}})
    assert failed.error and not failed.ends_turn
    assert failed.text == (
        "Not enough plants: need 2 mint, have 0; need 4 chamomile, have 0; need 2 rosemary, have 0. Nothing was brewed."
    )
    assert d.handle({"action": "brew", "recipe": {"mint": 1}}).text == "A recipe needs 2–4 distinct plants."


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
        "Growth:\n- sage: no planting finished yet\n- rosemary: no planting finished yet\n"
        "Interactions:\n"
        "- dill, elderberry, sage → +I\n"
        "- dill, (higher) elderberry, sage → +I"
    )
    both = d.handle({"tool": "kb_lookup", "plants": ["dill", "elderberry", "rosemary", "dill"]}).text
    assert both.split("Interactions:\n")[1] == (      # every interaction once, even if it names several plants

        "- dill, elderberry, mint → none\n"
        "- dill, elderberry, sage → +I\n"
        "- dill, (higher) elderberry, sage → +I"
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
    assert d.handle({"tool": "kb_lookup", "plants": ["dill"]}).text.endswith("Lore:\n- " + LORE[("dill", "elderberry")])
    assert d.handle({"tool": "kb_lookup", "plants": ["mint"]}).text.endswith("Lore: none yet.")
    act(d, {"action": "log", "potions": [{"id": 2}]})                      # adds dill+sage, elderberry+sage
    assert world.kb.lore("sage") == [LORE[("dill", "sage")], LORE[("elderberry", "sage")]]
    assert d.handle({"tool": "kb_lookup", "plants": ["dill", "sage"]}).text.endswith(
        "Lore:\n" + "\n".join("- " + LORE[pair] for pair in [("dill", "elderberry"), ("dill", "sage"), ("elderberry", "sage")])
    )
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
        ({"action": "log"}, '"potions" must be a non-empty list'),
        ({"action": "log", "potions": [{"id": 4}]}, "Unknown potion #4."),
        ({"action": "plant", "plots": {"x": {"plant": "mint", "soil": "brown"}}}, "A plot number must be a whole number"),
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


def test_mix_texts_and_inventory(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"sage": 1, "chamomile": 1, "nettle": 2, "mint": 1, "elderberry": 1})
    act(d, {"action": "brew", "recipes": [{"sage": 1, "chamomile": 1, "nettle": 1}, {"nettle": 1, "mint": 1, "elderberry": 1}]})
    text = act(d, {"action": "mix", "mixes": [[1, "2"]]})
    assert text == (
        'Mixed #1 + #2: {"sage": 1, "chamomile": 1, "nettle": 2, "mint": 1, "elderberry": 1} → '
        '{"positive": {}, "negative": {}, "secondary": ["fragrant", "warming", "sweet", "bitter", "toxic"]} (potion #3)'
    )
    assert world.turn == 3
    assert act(d, {"tool": "inventory"}) == "plants: none; potions: #3"
    failed = d.handle({"action": "mix", "mixes": [[1, 3]]})
    assert failed.error and not failed.ends_turn
    assert failed.text == "Potion #1 was already used up. Nothing was mixed."
    assert d.handle({"action": "mix", "mixes": [1, 3]}).text.startswith('"mixes" must be')
