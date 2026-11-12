"""The client's request (plain text for the agent, hidden translation for judging) and the judge."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from environment.brewer import PLANTS, STAT_SETS
from environment.inventory import Potion

TURNS_PER_DAY = 10
STAT_NAMES = {"I": "intelligence", "S": "strength", "V": "vitality", "D": "dexterity", "W": "wisdom"}
REQUESTS_FILE = Path(__file__).resolve().parent.parent / "content" / "requests.json"


@dataclass(frozen=True)
class Request:
    """text is what the agent reads; the other fields are its hidden translation."""

    id: str
    text: str
    stat: str
    threshold: int | None = None    # minimum positive intensity (%); None: any positive intensity
    deadline_day: int | None = None  # deliver by the end of this day; None: only the turn cap
    excluded: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.stat not in STAT_SETS:
            raise ValueError(f"Request {self.id}: unknown stat {self.stat}.")
        if self.threshold is not None and self.threshold <= 0:
            raise ValueError(f"Request {self.id}: the threshold must be > 0.")
        if self.deadline_day is not None and self.deadline_day < 1:
            raise ValueError(f"Request {self.id}: the deadline must be day 1 or later.")
        if unknown := sorted(self.excluded - set(PLANTS)):
            raise ValueError(f"Request {self.id}: unknown excluded plant {unknown[0]}.")
        if needed := sorted(self.excluded & set(STAT_SETS[self.stat])):
            raise ValueError(f"Request {self.id}: excluding {needed[0]} makes {self.stat} impossible.")

    @property
    def deadline_turn(self) -> int | None:
        """Day d ends with turn 10·d."""
        return None if self.deadline_day is None else self.deadline_day * TURNS_PER_DAY

    def describe(self) -> str:
        """The hidden translation, e.g. 'S >= +25% by day 7 (turn 70), without nettle'."""
        parts = [f"{self.stat} >= +{self.threshold}%" if self.threshold else f"any +{self.stat}"]
        if self.deadline_day is not None:
            parts.append(f"by day {self.deadline_day} (turn {self.deadline_turn})")
        if self.excluded:
            parts.append("without " + ", ".join(sorted(self.excluded)))
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "stat": self.stat,
            "threshold": self.threshold,
            "deadline_day": self.deadline_day,
            "excluded": sorted(self.excluded),
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "Request":
        return cls(
            data["id"], data["text"], data["stat"], data.get("threshold"), data.get("deadline_day"),
            frozenset(data.get("excluded", ())),
        )


def load_requests(path: Path = REQUESTS_FILE) -> dict[str, Request]:
    requests = [Request.from_dict(r) for r in json.loads(path.read_text(encoding="utf-8"))]
    by_id = {r.id: r for r in requests}
    if len(by_id) != len(requests):
        raise ValueError(f"Duplicate request ids in {path}.")
    return by_id


@dataclass(frozen=True)
class RequestResult:
    """How the request ended: the delivered potion (None if nothing was delivered in time)."""

    potion: int | None
    turn: int
    success: bool
    intensity: int              # positive intensity of the requested stat in the delivered potion
    failures: tuple[str, ...]   # why it failed (empty on success)

    def to_dict(self) -> dict:
        return {"potion": self.potion, "turn": self.turn, "success": self.success,
                "intensity": self.intensity, "failures": list(self.failures)}

    @classmethod
    def from_dict(cls, data: Mapping) -> "RequestResult":
        return cls(data["potion"], data["turn"], data["success"], data["intensity"], tuple(data["failures"]))


def potion_failures(request: Request, potion: Potion) -> list[str]:
    """Why this potion would fail the request (empty: it succeeds). Other primary effects are ignored."""
    failures = []
    value = potion.effect.positive.get(request.stat, 0)
    if value <= 0:
        failures.append(f"no positive {request.stat}")
    elif request.threshold is not None and value < request.threshold:
        failures.append(f"{request.stat} {value}% is below {request.threshold}%")
    if not potion.effect.drinkable:
        failures.append("undrinkable")
    if bad := sorted(request.excluded & potion.recipe.keys()):
        failures.append("contains " + ", ".join(bad))
    return failures


def judge(request: Request, potion: Potion | None, turn: int) -> RequestResult:
    """Judge a delivery (or, with potion None, the end of the episode without one)."""
    if potion is None:
        return RequestResult(None, turn, False, 0, ("nothing delivered",))
    failures = potion_failures(request, potion)
    return RequestResult(potion.id, turn, not failures, potion.effect.positive.get(request.stat, 0), tuple(failures))
