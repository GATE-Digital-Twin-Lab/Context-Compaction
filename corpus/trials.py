"""Layer 3b of the corpus pool: the trial ledgers (demo_spec.md, Sources).

One apothecary ledger per stat. Each entry is a trial: a drinker's work measured before and after
drinking a brew of the stat's plants, sometimes with a 2-plant brew poured into it, and what was noticed
while drinking. The counts in the brews are hidden choices: every base brew is one whose stat comes out at
10 or 20%, either way, and every result is computed by the brewer, so a ledger never contradicts the world.
The two numbers of the work give the result's intensity (2 stones -> 3 is +50%), so an agent can work out
how much a label changes a stat, and see that counts matter: an added plant can break the stat or turn it.

    python -m corpus.sheets         # the ledgers are written to content/sheets.json with the other sheets
"""

import random
from collections import Counter
from itertools import combinations, product

from corpus.catalogue import SEED, noticed
from corpus.myths import label_variants
from environment.brewer import MODIFIERS, PLANTS, STAT_SETS, apply_modifier, effect_of, net_modifier

BASE_LEVELS = (10, 20)          # the hidden base intensities a ledger uses (either sign)
MAX_COUNT = 4                   # counts of a base brew's plants, 1..MAX_COUNT
ROLES = ("alone", "boost", "weaken", "negative", "cancel", "counts")
BEFORE = (2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100)   # plausible counts of work
RATE = 0.8                      # an apothecary transcript's facts are correct at this rate
WORDS = (450, 650)
PADDING = 0.2


def signed(recipe: dict, stat: str) -> int:
    """The stat's intensity in a recipe, negative for a loss; 0 if it does not act."""
    effect = effect_of(recipe)
    return effect.positive.get(stat, 0) - effect.negative.get(stat, 0)


def bases(stat: str) -> list[tuple[dict, int]]:
    """Brews of exactly the stat's plants whose stat comes out at 10 or 20%, gained or lost."""
    plants = STAT_SETS[stat]
    out = []
    for counts in product(range(1, MAX_COUNT + 1), repeat=len(plants)):
        recipe = dict(zip(plants, counts))
        value = signed(recipe, stat)
        if abs(value) in BASE_LEVELS:
            out.append((recipe, value))
    return out


def _summed(*recipes: dict) -> dict:
    total = Counter()
    for recipe in recipes:
        total.update(recipe)
    return dict(total)


def _role(base: int, result: int, labels: list[str], added_plants: set[str], stat: str) -> str | None:
    """Why the result differs from the base. Label-driven roles need the result to be exactly base x the
    net modifier, with no rounding, so the arithmetic in a story is exact; anything else the added plants
    did (the stat gone, turned, stronger or weaker) is a lesson in counts."""
    if result and abs(result) < 5:
        return None                                    # too small for a story to show (100 -> 101)
    modifier = net_modifier(labels)
    exact = abs(base) * (100 + modifier) % 100 == 0
    expected = (1 if base > 0 else -1) * apply_modifier(abs(base), modifier)
    if result != expected:
        return "counts" if added_plants & set(STAT_SETS[stat]) else None
    if not exact:
        return None
    if labels and not noticed(labels):
        return "cancel"                                # labels met and cancelled: tastes like water
    if base < 0 and result != base:
        return "negative"                              # a loss, scaled the same way as a gain
    if base > 0 and result > base:
        return "boost"
    if base > 0 and result < base:
        return "weaken"
    return None


def candidates(stat: str) -> dict[str, list[dict]]:
    """Every trial the brewer allows, by role: a base brew alone, or with one 2-plant brew poured in.
    A trial where the mix also acts on another stat, or cannot be drunk, is left out."""
    by_role: dict[str, list[dict]] = {role: [] for role in ROLES}
    for base, value in bases(stat):
        if value > 0:
            by_role["alone"].append({"base": base, "added": [], "result": value, "labels": []})
        for pair in combinations(PLANTS, 2):
            added = dict.fromkeys(pair, 1)
            mixed = _summed(base, added)
            effect = effect_of(mixed)
            others = {s for s in (*effect.positive, *effect.negative) if s != stat}
            if others or not effect.drinkable:
                continue
            labels = list(effect.secondary)
            result = signed(mixed, stat)
            role = _role(value, result, labels, set(pair), stat)
            if role:
                by_role[role].append({"base": base, "added": [added], "result": result, "labels": labels,
                                      "base_value": value})
    return by_role


def _numbers(percent: int, rng: random.Random) -> tuple[int, int]:
    """A before and an after count of work, whole numbers, that differ by exactly this percent."""
    options = [b for b in BEFORE if b * (100 + percent) % 100 == 0 and b * (100 + percent) > 0]
    before = rng.choice(options)
    return before, before * (100 + percent) // 100


def _told(stat: str, percent: int, labels: list[str], rng: random.Random) -> dict:
    before, after = _numbers(percent, rng)
    return {"stat": stat if after != before else None, "before": before, "after": after, "noticed": labels}


def _myth(trial: dict, stat: str, rng: random.Random) -> dict:
    """A wrong record, one change from the truth: the work's numbers as if the net modifier were
    another (one label more or less, or the other base level), or another set of labels noticed."""
    base, result, labels = trial.get("base_value", trial["result"]), trial["result"], noticed(trial["labels"])
    sign = 1 if base > 0 else -1
    percents = set()
    if not trial["added"]:
        percents = {sign * level for level in BASE_LEVELS if sign * level != result}
    elif result and labels:
        mod = net_modifier(trial["labels"])
        for label in MODIFIERS:
            for alt in (mod + MODIFIERS[label], mod - MODIFIERS[label]):
                value = sign * apply_modifier(abs(base), alt)
                if value and value != result and alt > -100:
                    percents.add(value)
    options = [("numbers", p) for p in sorted(percents)]
    options += [("labels", v) for v in label_variants(labels, allow_empty=True)]
    what, value = rng.choice(options)
    if what == "numbers":
        return _told(stat, value, labels, rng)
    return {**trial["truth"], "noticed": value}


def _poured(trial: dict) -> tuple:
    return tuple(sorted(tuple(sorted(brew)) for brew in trial["added"]))


def ledger(stat: str, seed: int = SEED) -> dict:
    """The sheet of one stat's ledger: one trial per role the brewer allows, each on its own base brew
    where possible, so the ledger shows both base levels and both signs."""
    rng = random.Random(f"{seed}:trials:{stat}")
    pool = candidates(stat)
    used: list[dict] = []
    poured: set[tuple] = set()          # every trial pours a different brew, so a reader can tell them apart
    entries = []
    for role in ROLES:
        options = [t for t in pool[role] if _poured(t) not in poured]
        if not options:
            continue
        fresh = [t for t in options if t["base"] not in used] or options
        trial = dict(rng.choice(fresh))
        used.append(trial["base"])
        poured.add(_poured(trial))
        trial["truth"] = _told(stat, trial["result"], noticed(trial["labels"]), rng)
        true = rng.random() < RATE
        entry = {"fact": f"trial:{stat}:{role}", "type": "trial", "role": role, "true": true, "vague": False,
                 "base": trial["base"], "added": trial["added"], "result": trial["result"], "labels": trial["labels"],
                 "value": trial["truth"], "told": trial["truth"] if true else _myth(trial, stat, rng)}
        entries.append(entry)
    return {"id": f"trials:{stat}", "kind": "trials", "focus": stat, "words": rng.randint(*WORDS),
            "padding": PADDING, "facts": entries}


def ledgers(seed: int = SEED) -> list[dict]:
    return [ledger(stat, seed) for stat in STAT_SETS]
