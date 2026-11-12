"""Needed-facts ledger: derives the facts the agent should know from the world state."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from environment.inventory import Potion
from environment.world import World


class FactKind(StrEnum):
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
    """E.g. '+S 25%, -I 5% (fragrant)'."""
    effect = potion.effect
    parts = [f"+{s} {v}%" for s, v in effect.positive.items()] + [f"-{s} {v}%" for s, v in effect.negative.items()]
    text = ", ".join(parts) or "no effect"
    return f"{text} ({', '.join(effect.secondary)})" if effect.secondary else text


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

        # The request is in the system prompt (never compacted), so it is not a fact to retain.
        stat, excluded = world.request.stat, world.request.excluded
        candidates = [   # deliverable apart from the threshold
            p for p in world.inventory.held
            if p.effect.positive.get(stat, 0) > 0 and p.effect.drinkable and not excluded & p.recipe.keys()
        ]
        if candidates:
            potion = max(candidates, key=lambda p: (p.effect.positive[stat], -p.id))
            add(
                f"best:#{potion.id}",
                FactKind.BEST,
                f"Best held {stat} potion for the request so far: #{potion.id} ({recipe_text(potion)}) → "
                f"{effect_text(potion)}.",
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
