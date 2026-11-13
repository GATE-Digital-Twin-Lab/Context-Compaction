import pytest

from environment.records import RecordBook, RecordError
from environment.requests import Request
from environment.world import World
from tools.dispatcher import Dispatcher

POND = [
    {"type": "claim", "source": "S7", "quote": "nettle, water mint and elder crowd the mill pond",
     "says": {"name": "pond plant", "plant": p}, "trust": "high"}
    for p in ("nettle", "mint", "elderberry")
]
NEEDS_NETTLE = {"kind": "necessity", "effect": "+D", "pattern": {"nettle": "any"}}


@pytest.fixture
def world() -> World:
    return World.create(6, Request("maiden", "text", "D", excluded=frozenset({"mint", "elderberry"})), 100, seed=0)


def lookup(d: Dispatcher, **fields) -> str:
    return d.handle({"tool": "kb_lookup", **fields}).text


# --- writing records ------------------------------------------------------------------------


def test_ids_turns_and_references_within_a_batch(world):
    world.turn = 12
    records = world.record(POND + [
        {"type": "belief", "statement": NEEDS_NETTLE, "why": "the herbal says nettle gives quick feet", "from": ["c1"]},
        {"type": "requirement", "phrase": "every cup leaves me dizzy", "means": {"avoid": ["mint", "elderberry"]},
         "from": ["c1", "c2", "c3"], "why": "nettle is needed for D, so the sickness comes from the others"},
    ])
    assert [r.id for r in records] == ["c1", "c2", "c3", "b1", "r1"] and all(r.turn == 12 for r in records)
    assert world.record([{"type": "claim", "source": "S8", "quote": "q", "says": NEEDS_NETTLE, "trust": "low"}])[0].id == "c4"


def test_a_requirement_starts_open_and_is_refined():
    book = RecordBook()
    (r1,) = book.add([{"type": "requirement", "phrase": "plants on its banks... dizzy", "open": "which plants grow by the pond?"}], 1)
    assert r1.is_open
    (r2,) = book.add([{"type": "requirement", "phrase": "plants on its banks... dizzy", "means": {"avoid": ["mint"]},
                       "replaces": "r1"}], 13)
    assert r1.replaced_by == "r2" and not r1.is_open and not r2.is_open


@pytest.mark.parametrize(
    "record, message",
    [
        ({"type": "note"}, '"type" must be one of'),
        ({"type": "claim", "source": "S1", "quote": "q", "says": NEEDS_NETTLE}, 'needs "trust"'),
        ({"type": "claim", "source": "S1", "quote": "q", "says": NEEDS_NETTLE, "trust": "total"}, '"trust" must be'),
        ({"type": "claim", "source": "S1", "quote": "q", "says": {"name": "pond plant", "plant": "lotus"}, "trust": "low"}, "Unknown plant lotus"),
        ({"type": "claim", "source": "S1", "quote": "q", "says": {"name": "pond", "plants": ["mint"]}, "trust": "low"}, "A name claim is"),
        ({"type": "claim", "source": "S1", "quote": "q", "says": {"kind": "guess"}, "trust": "low"}, '"says": "kind" must be'),
        ({"type": "belief", "statement": NEEDS_NETTLE}, 'needs "why"'),
        ({"type": "belief", "statement": NEEDS_NETTLE, "why": " "}, '"why" must be a non-empty text'),
        ({"type": "belief", "statement": NEEDS_NETTLE, "why": "w", "from": ["c9"]}, "Unknown claim c9"),
        ({"type": "requirement", "phrase": "a week"}, 'needs "means", an "open" question, or both'),
        ({"type": "requirement", "phrase": "a week", "means": {"deadline": 70}}, 'Unknown field "deadline" in "means"'),
        ({"type": "requirement", "phrase": "a week", "means": {"stat": "X"}}, '"stat" must be one of'),
        ({"type": "requirement", "phrase": "p", "means": {"avoid": ["lotus"]}}, '"avoid" must be a list of plant names'),
        ({"type": "requirement", "phrase": "p", "open": "o", "replaces": "b1"}, "b1 is not a requirement"),
        ({"type": "claim", "source": "S1", "quote": "q", "says": NEEDS_NETTLE, "trust": "low", "page": 3}, 'Unknown field "page"'),
    ],
)
def test_invalid_records(world, record, message):
    world.record([{"type": "belief", "statement": NEEDS_NETTLE, "why": "w"}])
    with pytest.raises(RecordError, match=message):
        world.record([record])


def test_a_bad_record_writes_nothing_and_a_record_is_replaced_once(world):
    with pytest.raises(RecordError, match="Record 2:"):
        world.record([POND[0], {"type": "claim"}])
    assert world.records.records == []
    world.record([{"type": "requirement", "phrase": "p", "open": "o"}])
    world.record([{"type": "requirement", "phrase": "p", "means": {"stat": "D"}, "replaces": "r1"}])
    with pytest.raises(RecordError, match="r1 was already replaced"):
        world.record([{"type": "requirement", "phrase": "p", "means": {"stat": "D"}, "replaces": "r1"}])


def test_records_survive_a_checkpoint(world):
    world.record(POND + [{"type": "requirement", "phrase": "p", "open": "o"}])
    world.record([{"type": "requirement", "phrase": "p", "means": {"stat": "D"}, "replaces": "r1"}])
    copy = World.from_dict(world.to_dict())
    assert copy.records == world.records and copy.records.get("r1").replaced_by == "r2"


# --- the record tool, lookups and the budget ---------------------------------------------------


def test_record_tool_reports_ids_and_belief_status(world):
    d = Dispatcher(world)
    world.inventory.add_plants({"nettle": 2, "sage": 2, "rosemary": 4})
    d.handle({"action": "brew", "recipes": [{"nettle": 1, "sage": 1, "rosemary": 2}, {"sage": 1, "rosemary": 2}]})
    world.end_turn()
    result = d.handle({"tool": "record", "records": POND[:1] + [
        {"type": "belief", "statement": NEEDS_NETTLE, "why": "a source says so", "from": ["c1"]}]})
    assert result.text == (
        "Recorded:\n- c1\n"
        '- b1: {"status": "true", "for": [1], "against": [], "tested": 1}\n'
        "(4 of 5 record/validate calls left this turn.)"
    )
    bad = d.handle({"tool": "record", "records": [{"type": "belief"}]})
    assert bad.error and bad.text == 'A belief needs "statement". Nothing was recorded.'


def test_lookups_of_agent_records(world):
    d = Dispatcher(world)
    world.record(POND + [
        {"type": "claim", "source": "S9", "quote": "mint never grew by any pond", "says": {"name": "pond plant", "plant": "basil"},
         "trust": "low", "why": "a pamphlet"},
        {"type": "belief", "statement": NEEDS_NETTLE, "why": "S7 links nettle to the cure", "from": ["c1"]},
        {"type": "requirement", "phrase": "slow and heavy-limbed", "means": {"stat": "D"}},
        {"type": "requirement", "phrase": "plants on its banks", "open": "which plants are pond plants?"},
    ])
    assert lookup(d, type="claim", name="pond plant", trust="high").startswith("3 claim records:")
    assert lookup(d, type="claim", source="S9") == (
        '1 claim record:\n- c4 (turn 1, source S9, trust low): "mint never grew by any pond" → '
        '{"name": "pond plant", "plant": "basil"}; why: a pamphlet'
    )
    assert lookup(d, type="claim", plant="nettle").startswith("1 claim record:")
    assert lookup(d, type="belief", status="unknown") == (
        '1 belief record:\n- b1 (turn 1, unknown, tested 0): {"kind": "necessity", "effect": "+D", '
        '"pattern": {"nettle": "any"}}; from c1; why: S7 links nettle to the cure'
    )
    assert lookup(d, type="belief", status="true") == "No belief records match."
    assert lookup(d, type="requirement", open=True) == (
        '1 requirement record:\n- r2 (turn 1): "plants on its banks" → {}; open: which plants are pond plants?'
    )
    world.record([{"type": "requirement", "phrase": "plants on its banks", "means": {"avoid": ["mint", "elderberry"]},
                   "replaces": "r2", "from": ["c1", "c2", "c3"]}])
    assert lookup(d, type="requirement", open=True) == "No requirement records match."
    assert "r2 (turn 1, replaced by r3)" in lookup(d, type="requirement", replaced=True)
    assert "- r2 (" not in lookup(d, type="requirement") and "- r3 (turn 1, replaces r2)" in lookup(d, type="requirement")


def test_the_budget_allows_five_counted_calls_per_turn(world):
    d = Dispatcher(world)
    statement = {"kind": "soil", "plant": "dill", "soil": "brown", "claim": "always_dies"}
    for left in (4, 3, 2, 1, 0):
        assert d.handle({"tool": "validate", "statements": [statement]}).text.endswith(f"({left} of 5 record/validate calls left this turn.)")
    sixth = d.handle({"tool": "record", "records": POND[:1]})
    assert sixth.error and not sixth.ends_turn and "budget of 5 record/validate calls is used up" in sixth.text
    assert world.records.records == [] and world.turn == 1
    for _ in range(3):                                              # not failures: no forced skip
        assert not d.handle({"tool": "validate", "statements": [statement]}).ends_turn
    assert lookup(d, type="claim") == "No claim records match."     # free tools still work
    d.handle({"action": "skip"})
    world.end_turn()
    assert not d.handle({"tool": "record", "records": POND[:1]}).error   # a new turn, a new budget


def test_a_failed_counted_call_does_not_use_the_budget(world):
    d = Dispatcher(world)
    assert d.handle({"tool": "validate", "statements": [{"kind": "guess"}]}).error
    assert d.handle({"tool": "record", "records": POND[:1]}).text.endswith("(4 of 5 record/validate calls left this turn.)")
