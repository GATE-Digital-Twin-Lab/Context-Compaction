"""The validator: checks the agent's statements against the notebook's automatic records (potions and
growth), never against the hidden rules. Every answer is "true", "false" or "unknown", with the evidence.

Statement kinds (JSON):
  sufficiency  every potion matching the pattern has the effect
               {"kind": "sufficiency", "pattern": {"sage": "any", "chamomile": "any"}, "effect": "sweet"}
  necessity    every potion with the effect matches the pattern (a list of patterns means any of them)
               {"kind": "necessity", "effect": "+D", "pattern": {"nettle": "any"}}
  relation     a higher count of the plant never lowers (increases) or never raises (decreases) the stat,
               judged only on pairs of potions whose recipes differ in that plant's count alone
               {"kind": "relation", "plant": "chamomile", "effect": "+S", "direction": "increases"}
  soil         {"kind": "soil", "plant": "dill", "soil": "brown", "claim": "survival_at_least", "rate": 60}
               claims: always_dies, always_survives, survival_at_least / survival_at_most (+ "rate" in %),
               growth_time (+ "turns")
An effect is "+S" / "-I" (a stat with its sign; "at_least" sets a minimum intensity), "none" (no stat
effect) or a secondary label such as "sweet"; "not": true negates it. Drinkability is not observable,
so it is not an effect: the agent sees the labels (e.g. toxic) and the intensities."""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from environment.brewer import MODIFIERS, PLANTS, STAT_SETS
from environment.garden import Finished
from environment.inventory import Potion
from environment.notebook import Pattern, matches_any, parse_patterns
from environment.soils import SOILS

MAX_IDS = 10   # evidence lists are cut to this length; "tested" gives the full count
Z95 = 1.959964
KINDS = ("sufficiency", "necessity", "relation", "soil")
SOIL_CLAIMS = ("always_dies", "always_survives", "survival_at_least", "survival_at_most", "growth_time")


@dataclass(frozen=True)
class EffectTest:
    effect: str                  # "+S", "-S", "none" or a secondary label
    at_least: int | None = None  # minimum intensity, for a stat
    negated: bool = False

    def value(self, potion: Potion) -> int:
        """Intensity of the signed stat in the potion (0 if absent)."""
        side = potion.effect.positive if self.effect[0] == "+" else potion.effect.negative
        return side.get(self.effect[1:], 0)

    def holds(self, potion: Potion) -> bool:
        e = potion.effect
        if self.effect == "none":
            result = e.is_empty
        elif self.effect in MODIFIERS:
            result = self.effect in e.secondary
        else:
            result = self.value(potion) >= (self.at_least or 1)
        return result != self.negated


def parse_effect(s: Mapping, stat_only: bool = False) -> EffectTest:
    effect = s.get("effect")
    is_stat = isinstance(effect, str) and len(effect) == 2 and effect[0] in "+-" and effect[1:] in STAT_SETS
    if stat_only and not is_stat:
        raise ValueError('"effect" must be a stat with its sign, e.g. "+S".')
    if not (is_stat or effect == "none" or effect in MODIFIERS):
        raise ValueError(f'"effect" must be a stat with its sign ("+S", "-I"), "none", or a label ({", ".join(MODIFIERS)}).')
    at_least = s.get("at_least")
    if at_least is not None:
        if not is_stat:
            raise ValueError('"at_least" needs a stat effect such as "+S".')
        if isinstance(at_least, bool) or not isinstance(at_least, int) or at_least < 1:
            raise ValueError('"at_least" must be a whole number >= 1.')
    negated = s.get("not", False)
    if not isinstance(negated, bool):
        raise ValueError('"not" must be true or false.')
    return EffectTest(effect, at_least, negated)


def _ids(potions: Iterable[Potion]) -> list[int]:
    return [p.id for p in potions][:MAX_IDS]


def _answer(status: str, **evidence) -> dict:
    return {"status": status, **evidence}


# --- potion statements ------------------------------------------------------------------------


def sufficiency(patterns: Sequence[Pattern], effect: EffectTest, potions: Sequence[Potion]) -> dict:
    tested = [p for p in potions if matches_any(patterns, p.recipe)]
    good = [p for p in tested if effect.holds(p)]
    bad = [p for p in tested if not effect.holds(p)]
    status = "false" if bad else "true" if tested else "unknown"
    return _answer(status, **{"for": _ids(good), "against": _ids(bad), "tested": len(tested)})


def necessity(patterns: Sequence[Pattern], effect: EffectTest, potions: Sequence[Potion]) -> dict:
    """Refuted by a potion with the effect that does not match; "tested" counts the potions that do not
    match (the ones that could refute it). True needs a witness with the effect and at least one test."""
    with_effect = [p for p in potions if effect.holds(p)]
    good = [p for p in with_effect if matches_any(patterns, p.recipe)]
    bad = [p for p in with_effect if not matches_any(patterns, p.recipe)]
    tested = [p for p in potions if not matches_any(patterns, p.recipe)]
    status = "false" if bad else "true" if good and tested else "unknown"
    return _answer(status, **{"for": _ids(good), "against": _ids(bad), "tested": len(tested)})


def relation(plant: str, effect: EffectTest, increases: bool, potions: Sequence[Potion]) -> dict:
    """Pairs (a, b) whose recipes differ only in the plant's count (0 allowed), with a having fewer."""
    agree, against, flat, confounded = [], [], [], 0
    for i, a in enumerate(potions):
        for b in potions[i + 1:]:
            na, nb = a.recipe.get(plant, 0), b.recipe.get(plant, 0)
            if na == nb:
                continue
            rest_a = {p: n for p, n in a.recipe.items() if p != plant}
            rest_b = {p: n for p, n in b.recipe.items() if p != plant}
            if rest_a != rest_b:
                confounded += 1
                continue
            low, high = (a, b) if na < nb else (b, a)
            change = effect.value(high) - effect.value(low)
            pair = [low.id, high.id]
            if change == 0:
                flat.append(pair)
            elif (change > 0) == increases:
                agree.append(pair)
            else:
                against.append(pair)
    tested = len(agree) + len(against) + len(flat)
    status = "false" if against else "true" if tested else "unknown"
    return _answer(status, **{"for": agree[:MAX_IDS], "against": against[:MAX_IDS], "flat": flat[:MAX_IDS],
                              "tested": tested, "confounded": confounded})


# --- soil statements --------------------------------------------------------------------------


def wilson(successes: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    p = successes / n
    denom = 1 + Z95 ** 2 / n
    centre = (p + Z95 ** 2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n ** 2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def soil(plant: str, soil_name: str, claim: str, value: int | None, history: Iterable[Finished]) -> dict:
    done = [f for f in history if f.plant == plant and f.soil == soil_name]
    grew = sum(f.survived for f in done)
    died = len(done) - grew
    evidence = {"grew": grew, "died": died, "tested": len(done)}
    if not done:
        return _answer("unknown", **evidence)
    if claim == "always_dies":
        return _answer("false" if grew else "true", **evidence)
    if claim == "always_survives":
        return _answer("false" if died else "true", **evidence)
    if claim == "growth_time":
        times = sorted({f.done_turn - f.planted_turn for f in done})
        return _answer("true" if times == [value] else "false", **evidence, times=times)
    low, high = wilson(grew, len(done))
    rate = value / 100
    interval = [round(100 * low, 1), round(100 * high, 1)]
    if claim == "survival_at_least":
        status = "true" if low > rate else "false" if high < rate else "unknown"
    else:
        status = "true" if high < rate else "false" if low > rate else "unknown"
    return _answer(status, **evidence, interval=interval)


# --- entry point ------------------------------------------------------------------------------


def check(statement: Mapping, potions: Sequence[Potion], history: Iterable[Finished]) -> dict:
    """Evaluate one statement. Raises ValueError for a malformed statement."""
    if not isinstance(statement, Mapping):
        raise ValueError("A statement must be an object.")
    kind = statement.get("kind")
    if kind not in KINDS:
        raise ValueError(f'"kind" must be one of: {", ".join(KINDS)}.')
    if kind in ("sufficiency", "necessity"):
        if "pattern" not in statement:
            raise ValueError(f'A {kind} statement needs a "pattern".')
        patterns, effect = parse_patterns(statement["pattern"]), parse_effect(statement)
        return (sufficiency if kind == "sufficiency" else necessity)(patterns, effect, potions)
    if kind == "relation":
        plant, direction = statement.get("plant"), statement.get("direction")
        if plant not in PLANTS:
            raise ValueError(f"Unknown plant {plant}.")
        if direction not in ("increases", "decreases"):
            raise ValueError('"direction" must be "increases" or "decreases".')
        return relation(plant, parse_effect(statement, stat_only=True), direction == "increases", potions)
    plant, soil_name, claim = statement.get("plant"), statement.get("soil"), statement.get("claim")
    if plant not in PLANTS:
        raise ValueError(f"Unknown plant {plant}.")
    if soil_name not in SOILS:
        raise ValueError(f'"soil" must be one of: {", ".join(SOILS)}.')
    if claim not in SOIL_CLAIMS:
        raise ValueError(f'"claim" must be one of: {", ".join(SOIL_CLAIMS)}.')
    value = None
    if claim.startswith("survival"):
        value = statement.get("rate")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 100:
            raise ValueError('"rate" must be a whole percentage between 1 and 99.')
    elif claim == "growth_time":
        value = statement.get("turns")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError('"turns" must be a whole number >= 1.')
    return soil(plant, soil_name, claim, value, history)
