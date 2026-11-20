"""An episode's sample of the source pool (demo_spec.md, Sources: Sampling).

  1. The five trial ledgers are always in (they are the only source of intensities).
  2. The rest of the sample is split over the other kinds in proportion to the pool (largest remainder),
     so no kind is over-represented: with 200 of 357 every kind gets at most 200/357 of its pool
     (4 books, 35 transcripts, 22 herbal tales, 67 pamphlets, 67 folk tales).
  3. Repair: every alias and group (the non-experimental facts) must have a true source in the sample. An
     uncovered fact swaps in a pool source stating its truth, trying the least reliable kind first (folk tale,
     pamphlet, herbal tale, transcript, book), for a sampled source of the same kind whose removal leaves
     no other fact uncovered. A swap keeps every kind's count, so the quotas still hold.

  python -m corpus.sampler [seed] [size]    prints the sample's make-up"""

import json
import random
import sys
from collections import Counter
from math import floor
from pathlib import Path

from corpus.catalogue import CONTENT

SHEETS_FILE = CONTENT / "sheets.json"
SIZE = 200
ALWAYS = "trials"
REPAIR_ORDER = ("folk", "pamphlet", "herbal", "transcript", "book")   # least reliable first
NON_EXPERIMENTAL = ("alias", "group")


def load_sheets(path: Path = SHEETS_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def quotas(pool: Counter, size: int) -> dict[str, int]:
    """Sources per kind: every ledger, the rest by largest remainder over the other kinds."""
    fixed = pool[ALWAYS]
    if not fixed <= size <= sum(pool.values()):
        raise ValueError(f"A sample must hold between {fixed} and {sum(pool.values())} sources, not {size}.")
    kinds = sorted(k for k in pool if k != ALWAYS)
    rest, total = size - fixed, sum(pool[k] for k in kinds)
    shares = {k: rest * pool[k] / total for k in kinds}
    counts = {k: floor(v) for k, v in shares.items()}
    by_remainder = sorted(kinds, key=lambda k: (-(shares[k] - counts[k]), k))
    for k in by_remainder[: rest - sum(counts.values())]:
        counts[k] += 1
    return {ALWAYS: fixed, **counts}


def true_facts(sheet: dict) -> set[str]:
    """The non-experimental facts a sheet states truly ("alias:Ferrow", "group:Brackley:mint")."""
    return {f["fact"] for f in sheet["facts"] if f["type"] in NON_EXPERIMENTAL and f["true"]}


def sample(seed: int, size: int = SIZE, sheets: list[dict] | None = None) -> list[str]:
    """Sheet ids of the sample, in a shuffled order (the order gives the episode's source ids)."""
    sheets = load_sheets() if sheets is None else sheets
    rng = random.Random(seed)
    by_kind: dict[str, list[dict]] = {}
    for s in sheets:
        by_kind.setdefault(s["kind"], []).append(s)
    quota = quotas(Counter({k: len(v) for k, v in by_kind.items()}), size)
    chosen = {s["id"] for k, n in quota.items() for s in rng.sample(by_kind[k], n)}
    _repair(chosen, sheets, rng)
    order = sorted(chosen)
    rng.shuffle(order)
    return order


def _repair(chosen: set[str], sheets: list[dict], rng: random.Random) -> None:
    by_id = {s["id"]: s for s in sheets}
    facts = sorted({f["fact"] for s in sheets for f in s["facts"] if f["type"] in NON_EXPERIMENTAL})
    cover = Counter(f for sid in chosen for f in true_facts(by_id[sid]))
    for fact in facts:
        if cover[fact]:
            continue
        for kind in REPAIR_ORDER:
            incoming = sorted(s["id"] for s in sheets
                              if s["kind"] == kind and s["id"] not in chosen and fact in true_facts(s))
            outgoing = sorted(sid for sid in chosen if by_id[sid]["kind"] == kind
                              and all(cover[f] > 1 for f in true_facts(by_id[sid])))
            if incoming and outgoing:
                new, old = rng.choice(incoming), rng.choice(outgoing)
                chosen.remove(old)
                chosen.add(new)
                cover.subtract(true_facts(by_id[old]))
                cover.update(true_facts(by_id[new]))
                break
        else:
            raise ValueError(f"No source in the pool can give {fact} a true source.")


def main(argv: list[str]) -> None:
    seed = int(argv[0]) if argv else 0
    size = int(argv[1]) if len(argv) > 1 else SIZE
    sheets = load_sheets()
    kind_of = {s["id"]: s["kind"] for s in sheets}
    ids = sample(seed, size, sheets)
    print(f"seed {seed}: {len(ids)} sources", dict(Counter(kind_of[i] for i in ids)))
    print("books:", ", ".join(sorted(i for i in ids if kind_of[i] == "book")))


if __name__ == "__main__":
    main(sys.argv[1:])
