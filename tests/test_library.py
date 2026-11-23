from collections import Counter

import pytest

from corpus.sampler import NON_EXPERIMENTAL, load_sheets, quotas, sample, true_facts
from environment.library import Library, passages_of, tokens
from environment.requests import Request
from environment.world import World
from input import ExperimentConfig, parse_args
from tools.dispatcher import Dispatcher

SHEETS = load_sheets()
BY_ID = {s["id"]: s for s in SHEETS}
POOL = Counter(s["kind"] for s in SHEETS)


def test_quotas_of_200_keep_every_kind_within_its_share_and_every_ledger():
    q = quotas(POOL, 200)
    assert q == {"trials": 5, "book": 4, "folk": 67, "herbal": 22, "pamphlet": 67, "transcript": 35}
    for kind, n in q.items():
        if kind != "trials":
            assert n <= 200 / 357 * POOL[kind]


@pytest.mark.parametrize("seed", range(5))
def test_a_sample_keeps_its_quotas_and_gives_every_alias_and_group_a_true_source(seed):
    ids = sample(seed, sheets=SHEETS)
    assert len(ids) == len(set(ids)) == 200
    assert Counter(BY_ID[i]["kind"] for i in ids) == quotas(POOL, 200)
    every = {f["fact"] for s in SHEETS for f in s["facts"] if f["type"] in NON_EXPERIMENTAL}
    assert set().union(*(true_facts(BY_ID[i]) for i in ids)) == every


def test_a_sample_depends_only_on_its_seed():
    assert sample(3, sheets=SHEETS) == sample(3, sheets=SHEETS)
    assert sample(3, sheets=SHEETS) != sample(4, sheets=SHEETS)


def test_tokens_drop_stopwords_possessives_and_plurals():
    assert tokens("The nettles of Saint Brede's sprig") == ["nettle", "saint", "brede", "sprig"]


def test_passages_stay_short_and_headings_join_the_next_paragraph():
    body = "Monday.\n\n" + "\n".join(["one two three four five six seven eight nine ten."] * 12) + "\n\nShort end."
    parts = passages_of(body)
    assert parts[0].startswith("Monday.\n\n")
    assert all(len(p.split()) <= 90 for p in parts)
    assert "".join(parts).replace("\n", "").replace(" ", "") == body.replace("\n", "").replace(" ", "")


@pytest.fixture(scope="module")
def library() -> Library:
    return Library.create(0)


def test_sources_get_hidden_ids_and_show_their_header_kind(library):
    assert list(library.sources) == [f"S{i}" for i in range(1, 201)]
    kinds = Counter(s.kind for s in library.sources.values())
    assert kinds["apothecary transcript"] == 40          # the 5 ledgers show as transcripts
    assert "trials" not in " ".join(s.header() for s in library.sources.values())


def test_search_ranks_sources_by_their_decayed_passage_scores(library):
    hits = library.search("Saint Brede's sprig", 5)
    assert len(hits) == 5 and len({h.source.id for h in hits}) == 5
    assert "Saint Brede's sprig" in hits[0].source.body
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    top = library.passage_scores("Saint Brede's sprig")[:20]
    best = top[0][0]
    for h in hits:   # s1 + s2/2 + s3/4 ... over the source's candidate passages, normalised by the best
        mine = [s / best for s, i in top if library._passages[i].source.id == h.source.id]
        assert h.score == pytest.approx(sum(s * 0.5 ** j for j, s in enumerate(mine)))
        assert h.score < 2


def test_a_title_counts_once_and_can_match_alone(library):
    src = library.sources["S1"]
    hits = library.search(src.title, 200)
    assert src.id in [h.source.id for h in hits]
    assert sum(1 for p in library._passages if p.source.id == src.id and p.number == 0) == 1


def test_search_returns_fewer_sources_when_few_match(library):
    assert library.search("zzzz", 5) == []


def world_with_sources() -> World:
    return World.create(7, Request("s20", "text", "S", threshold=20), 100, seed=0, corpus_seed=0)


def test_read_needs_a_search_in_the_same_turn():
    world = world_with_sources()
    d = Dispatcher(world)
    found = d.handle({"tool": "search", "queries": ["mill pond"]}).text
    assert "(4 of 5 search/record/validate calls left this turn.)" in found
    assert "passage" not in found
    sid = found.split("Readable whole this turn with read: ")[1].split(",")[0].split(".")[0]
    text = d.handle({"tool": "read", "sources": [sid]})
    assert not text.error and text.text.startswith(f"{sid}: ")
    world.end_turn()
    again = d.handle({"tool": "read", "sources": [sid]})
    assert again.error and "search for it again" in again.text


def test_search_rejects_too_many_queries_and_episodes_without_sources():
    d = Dispatcher(world_with_sources())
    assert d.handle({"tool": "search", "queries": ["a", "b", "c", "d"]}).error
    bare = Dispatcher(World.create(7, Request("s20", "text", "S", threshold=20), 100, seed=0))
    assert "no sources" in bare.handle({"tool": "search", "queries": ["sage"]}).text


def test_the_library_survives_a_checkpoint():
    world = world_with_sources()
    Dispatcher(world).handle({"tool": "search", "queries": ["sage"]})
    back = World.from_dict(world.to_dict())
    assert back.library.to_dict() == world.library.to_dict()
    assert list(back.library.sources.values()) == list(world.library.sources.values())


def test_config_draws_a_corpus_seed_and_old_params_load_without_one(tmp_path):
    config = parse_args(["--env-seed", "1"])
    assert isinstance(config.corpus_seed, int) and config.corpus_size == 200
    assert parse_args(["--no-sources"]).corpus_seed is None
    data = config.to_dict()
    del data["corpus_seed"], data["corpus_size"]
    old = ExperimentConfig.from_dict(data)
    assert old.corpus_seed is None and old.corpus_size == 200


def test_a_claim_must_cite_a_source_of_the_sample():
    d = Dispatcher(world_with_sources())
    claim = {"type": "claim", "quote": "q", "says": {"name": "Ferrow", "plant": "mint"}, "trust": "low"}
    bad = d.handle({"tool": "record", "records": [{**claim, "source": "S999"}]})
    assert bad.error and "Unknown source S999" in bad.text
    assert not d.handle({"tool": "record", "records": [{**claim, "source": "S12"}]}).error


def test_the_system_prompt_carries_the_glossary_and_the_search_tools():
    from LLM.episode import system_prompt
    from input import parse_args
    text = system_prompt(parse_args([]).prompt_file.read_text(encoding="utf-8"), "my request")
    assert "<<glossary>>" not in text and "- S, strength (" in text and "a feeble grip" in text
    assert '{"tool": "search"' in text and '{"tool": "read"' in text
    assert "honeycomb" not in text   # the writers' near words stay hidden
    assert text.endswith("# The request\n\nmy request\n")
