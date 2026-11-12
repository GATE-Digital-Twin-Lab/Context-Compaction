"""Needed-facts ledger: derives the facts the agent should know from the world state."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from environment.goals import score_goal
from environment.inventory import Potion
from environment.world import World


class FactKind(StrEnum):
    ALLERGY = "allergy"
    GOAL = "goal"
    GOAL_DONE = "goal_done"
    BREW = "brew"
    BEST = "best"
    PLANTING = "planting"
    GROWTH = "growth"
    LORE = "lore"


RECOVERABLE = {FactKind.PLANTING, FactKind.GROWTH, FactKind.LORE}


@dataclass(frozen=True)
class Fact:
    id: str     # stable key, e.g. "potion:3", "planting:5@3"
    kind: FactKind
    text: str
    turn: int   # turn the fact appeared

    @property
    def recoverable(self) -> bool:
        return self.kind in RECOVERABLE


def recipe_text(potion: Potion) -> str:
    return ", ".join(f"{p}={n}" for p, n in sorted(potion.recipe.items()))


def effect_text(potion: Potion) -> str:
    effect = potion.effect
    if effect.positive:
        stat, value = next(iter(effect.positive.items()))
        return f"+{stat} {value}%"
    if effect.negative:
        stat, value = next(iter(effect.negative.items()))
        return f"-{stat} {value}%"
    return "no effect"


@dataclass
class Ledger:
    """Call observe() at the start of every turn; snapshot() at a compaction point."""

    _seen: dict[str, Fact] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"seen": [asdict(f) for f in self._seen.values()]}

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        seen = {f["id"]: Fact(f["id"], FactKind(f["kind"]), f["text"], f["turn"]) for f in data["seen"]}
        return cls(seen)

    def observe(self, world: World) -> list[Fact]:
        """Return facts that are new since the last call."""
        new = [f for f in self._active(world) if f.id not in self._seen]
        for fact in new:
            self._seen[fact.id] = fact
        return new

    def snapshot(self, world: World) -> list[dict]:
        """Active facts with whether the knowledge base holds them (plantings are in the garden line,
        growth records and lore are written automatically)."""
        rows = []
        for fact in self._active(world):
            logged = True if fact.recoverable else None
            rows.append({**asdict(fact), "recoverable": fact.recoverable, "logged": logged})
        return rows

    def _active(self, world: World) -> list[Fact]:
        """Facts that are currently needed, keeping the turn they first appeared."""
        facts: list[Fact] = []

        def add(id_: str, kind: FactKind, text: str, turn: int) -> None:
            facts.append(self._seen.get(id_) or Fact(id_, kind, text, turn))

        if world.allergy is not None:
            a, b = sorted(world.allergy.plants)
            add("allergy", FactKind.ALLERGY, f"The user is allergic to the combination of {a} and {b}.", 0)

        for i, result in enumerate(world.results, start=1):
            add(f"goal_done:{i}", FactKind.GOAL_DONE, f"Goal {i} ({result.goal.describe()}) is finished.", result.end_turn)

        goal = world.current_goal
        if goal is not None:
            i, start = world.goal_index + 1, world.goal_start
            text = f"Current goal (goal {i}, started turn {start}): {goal.describe()}."
            if goal.turns is not None:
                text = text[:-1] + f" (ends after turn {start + goal.turns - 1})."
            add(f"goal:{i}", FactKind.GOAL, text, start)
            best = score_goal(goal, world.inventory.potions, world.allergy, start, world.turn)
            if best.best_potion is not None:
                potion = world.inventory.potions[best.best_potion - 1]
                add(
                    f"best:{i}:#{potion.id}",
                    FactKind.BEST,
                    f"Best valid {goal.stat} potion for the current goal so far: "
                    f"#{potion.id} ({recipe_text(potion)}) → {effect_text(potion)}.",
                    potion.turn,
                )

        for potion in world.inventory.potions:
            add(
                f"potion:{potion.id}",
                FactKind.BREW,
                f"Potion #{potion.id} (turn {potion.turn}): {recipe_text(potion)} → {effect_text(potion)}.",
                potion.turn,
            )

        for plot, (plant, soil, planted) in world.garden.plantings().items():
            add(f"planting:{plot}@{planted}", FactKind.PLANTING,
                f"Plot {plot} contains {plant} in {soil} soil (planted turn {planted}).", planted)

        for f in world.garden.history:  # one fact per (plant, soil) and outcome, from its first occurrence
            g = f.done_turn - f.planted_turn
            outcome = "grows" if f.survived else "died"
            add(f"growth:{f.plant}:{f.soil}:{outcome}", FactKind.GROWTH,
                f"{f.plant} in {f.soil} soil {outcome} after {g} turn{'s' if g != 1 else ''}.", f.done_turn)

        for a, b, text, turn in world.kb.lore_entries():
            add(f"lore:{a}+{b}", FactKind.LORE, f"Lore on {a} and {b}: {text}", turn)

        return facts
