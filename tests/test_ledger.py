from environment.goals import Allergy, Goal, GoalKind
from environment.world import World
from ledger import FactKind, Ledger
from tools.dispatcher import Dispatcher

GROWTH = {"p1": 3, "p2": 4, "p3": 3, "p4": 2, "p5": 3, "p6": 3, "p7": 6, "p8": 3}
STRENGTH_10 = Goal(GoalKind.TARGET, "S", target=10)
INTEL_30 = Goal(GoalKind.TIME, "I", turns=30)


def setup(goals=(STRENGTH_10, INTEL_30), allergy=Allergy(frozenset({"p3", "p5"}))):
    world = World.create(7, (2, 6), list(goals), allergy, 100, seed=0)
    world.garden.growth_times = dict(GROWTH)
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


def test_initial_facts():
    world, _, ledger = setup()
    texts = [r["text"] for r in active(ledger, world)]
    assert texts == [
        "The user is allergic to the combination of p3 and p5.",
        "Current goal (goal 1, started turn 1): brew a strength (S) potion of at least +10% as fast as you can.",
    ]
    assert all(not r["recoverable"] and r["logged"] is None for r in active(ledger, world))


def test_planting_and_growth_facts_lifecycle():
    world, d, ledger = setup()
    new = act(world, d, ledger, {"action": "plant", "plots": {"1": "p4"}})       # turn 1
    assert [f.text for f in new] == ["Plot 1 contains p4 (planted turn 1)."]
    assert active(ledger, world, FactKind.PLANTING)[0]["logged"] is False
    new = act(world, d, ledger, {"action": "skip"})                                # turn 2 → p4 ready at 3
    assert [(f.text, f.turn) for f in new] == [("p4 grows in 2 turns.", 3)]
    act(world, d, ledger, {"action": "log", "garden": True})                       # turn 3
    assert active(ledger, world, FactKind.PLANTING)[0]["logged"] is True
    assert active(ledger, world, FactKind.GROWTH)[0]["logged"] is True
    act(world, d, ledger, {"action": "gather"})                                    # turn 4
    assert active(ledger, world, FactKind.PLANTING) == []                          # retired on gather
    assert len(active(ledger, world, FactKind.GROWTH)) == 1                        # growth stays


def test_brews_best_and_allergy():
    world, d, ledger = setup()
    world.inventory.add_plants({"p1": 6, "p5": 5, "p8": 6, "p3": 1})
    act(world, d, ledger, {"action": "brew", "recipe": {"p1": 2, "p5": 1, "p8": 2}})   # +S 2%
    best = active(ledger, world, FactKind.BEST)
    assert [r["text"] for r in best] == [
        "Best valid S potion for the current goal so far: #1 (p1=2, p5=1, p8=2) → +S 2%."
    ]
    act(world, d, ledger, {"action": "brew", "recipe": {"p1": 2, "p5": 2, "p8": 2}})   # +S 5%
    assert [r["id"] for r in active(ledger, world, FactKind.BEST)] == ["best:1:#2"]
    act(world, d, ledger, {"action": "brew", "recipe": {"p1": 2, "p5": 2, "p8": 2, "p3": 1}})  # allergic
    assert [r["id"] for r in active(ledger, world, FactKind.BEST)] == ["best:1:#2"]
    brews = [r["text"] for r in active(ledger, world, FactKind.BREW)]
    assert brews[2] == "Potion #3 (turn 3): p1=2, p3=1, p5=2, p8=2 → +S 5%."


def test_goal_switch():
    world, d, ledger = setup(allergy=None)
    world.inventory.add_plants({"p1": 2, "p5": 3, "p8": 2})
    new = act(world, d, ledger, {"action": "brew", "recipe": {"p1": 2, "p5": 3, "p8": 2}})  # +S 10%
    kinds = {f.kind: f for f in new}
    assert kinds[FactKind.GOAL_DONE].text == (
        "Goal 1 (brew a strength (S) potion of at least +10% as fast as you can) is finished."
    )
    assert kinds[FactKind.GOAL].text == (
        "Current goal (goal 2, started turn 2): brew the best intelligence (I) potion "
        "you can in 30 turns (ends after turn 31)."
    )
    assert active(ledger, world, FactKind.BEST) == []        # best of goal 1 no longer active
    assert len(active(ledger, world, FactKind.BREW)) == 1    # brews always stay


def test_observe_reports_each_fact_once():
    world, d, ledger = setup()
    act(world, d, ledger, {"action": "plant", "plots": {"1": "p7"}})
    assert act(world, d, ledger, {"action": "skip"}) == []
