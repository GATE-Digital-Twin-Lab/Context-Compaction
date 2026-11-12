from environment.requests import Request
from environment.world import World
from ledger import FactKind, Ledger
from tools.dispatcher import Dispatcher

S10_NO_NETTLE = Request("s10", "text", "S", threshold=10, excluded=frozenset({"nettle"}))


def setup(request=S10_NO_NETTLE):
    world = World.create(7, request, 100, seed=0)
    ledger = Ledger()
    ledger.observe(world)
    return world, Dispatcher(world), ledger


def act(world, d, ledger, call):
    """One action, end of turn, then the start-of-turn observation."""
    if d.handle(call).ends_turn:
        world.end_turn()
    return ledger.observe(world)


def active(ledger, world, kind=None):
    return [r for r in ledger.snapshot(world) if kind is None or r["kind"] == kind]


def test_no_facts_at_the_start():
    world, _, ledger = setup()
    assert active(ledger, world) == []   # the request is in the system prompt, not a fact to retain


def test_planting_and_growth_facts_lifecycle():
    world, d, ledger = setup()
    plots = {"1": {"plant": "sage", "soil": "yellow"}, "2": {"plant": "elderberry", "soil": "brown"}}
    new = act(world, d, ledger, {"action": "plant", "plots": plots})                # turn 1
    assert [f.text for f in new] == [
        "Plot 1 contains sage in yellow soil (planted turn 1).",
        "Plot 2 contains elderberry in brown soil (planted turn 1).",
    ]
    assert active(ledger, world, FactKind.PLANTING)[0]["logged"] is True           # shown in the garden line
    new = act(world, d, ledger, {"action": "skip"})                                # turn 2 → both finish at 3
    assert [(f.text, f.turn) for f in new] == [
        ("sage in yellow soil grows after 2 turns.", 3),
        ("elderberry in brown soil died after 2 turns.", 3),
    ]
    assert len(active(ledger, world, FactKind.PLANTING)) == 2                      # the dead plant stays until gathered
    assert all(r["logged"] for r in active(ledger, world, FactKind.GROWTH))        # recorded automatically
    act(world, d, ledger, {"tool": "gather"})
    assert active(ledger, world, FactKind.PLANTING) == []                          # retired on gather
    assert len(active(ledger, world, FactKind.GROWTH)) == 2                        # growth stays


def test_brews_and_the_best_deliverable_potion():
    world, d, ledger = setup()
    world.inventory.add_plants({"mint": 6, "chamomile": 5, "rosemary": 6, "nettle": 1})
    act(world, d, ledger, {"action": "brew", "recipe": {"mint": 2, "chamomile": 1, "rosemary": 2}})   # +S 2%
    best = active(ledger, world, FactKind.BEST)
    assert [r["text"] for r in best] == [
        "Best held S potion for the request so far: #1 (chamomile=1, mint=2, rosemary=2) → +S 2%."
    ]
    act(world, d, ledger, {"action": "brew", "recipe": {"mint": 2, "chamomile": 2, "rosemary": 2}})   # +S 5%
    assert [r["id"] for r in active(ledger, world, FactKind.BEST)] == ["best:#2"]
    act(world, d, ledger, {"action": "brew", "recipe": {"mint": 2, "chamomile": 2, "rosemary": 2, "nettle": 1}})  # +S 8%, nettle
    assert [r["id"] for r in active(ledger, world, FactKind.BEST)] == ["best:#2"]   # nettle is excluded
    brews = [r["text"] for r in active(ledger, world, FactKind.BREW)]
    assert brews[2] == "Potion #3 (turn 3): chamomile=2, mint=2, nettle=1, rosemary=2 → +S 8% (warming)."


def test_a_used_potion_is_no_longer_the_best():
    world, d, ledger = setup()
    world.inventory.add_plants({"mint": 2, "chamomile": 2, "rosemary": 2, "elderberry": 1, "dill": 1})
    act(world, d, ledger, {"action": "brew", "recipes": [{"mint": 2, "chamomile": 2, "rosemary": 2}, {"elderberry": 1, "dill": 1}]})
    assert [r["id"] for r in active(ledger, world, FactKind.BEST)] == ["best:#1"]
    act(world, d, ledger, {"action": "mix", "mixes": [[1, 2]]})   # S 5% with bitter, sweet, bitter: they cancel
    assert [r["id"] for r in active(ledger, world, FactKind.BEST)] == ["best:#3"]


def test_observe_reports_each_fact_once():
    world, d, ledger = setup()
    act(world, d, ledger, {"action": "plant", "plots": {"1": {"plant": "basil", "soil": "brown"}}})
    assert act(world, d, ledger, {"action": "skip"}) == []


def test_potion_facts_are_recoverable_from_the_notebook():
    world, d, ledger = setup()
    world.inventory.add_plants({"elderberry": 1, "sage": 1, "dill": 1})
    act(world, d, ledger, {"action": "brew", "recipe": {"elderberry": 1, "sage": 1, "dill": 1}})
    assert all(r["recoverable"] and r["logged"] for r in active(ledger, world, FactKind.BREW))
