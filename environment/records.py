"""The agent's own notebook records: claims (what a source says), beliefs (the agent's hypotheses, judged
by the validator) and requirements (what the request means). Append-only: a correction is a new record
that replaces an older one of the same type, which stays, marked as replaced.

  claim        {"type": "claim", "source": "S7", "quote": "...", "says": <statement or name>, "trust": "high"}
               says: a validator statement, or {"name": "pond plant", "plant": "nettle"}
  belief       {"type": "belief", "statement": <validator statement>, "why": "...", "from": ["c3"]}
  requirement  {"type": "requirement", "phrase": "...", "means": {"stat": "D", "at_least": 25,
                "deadline_turn": 70, "avoid": ["mint"]}, "open": "...", "from": ["c3"]}
Every record may give "replaces" (an id of the same type); "why" is required for beliefs, optional otherwise."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from environment.brewer import PLANTS, STAT_SETS
from environment.validator import check

TYPES = {"claim": "c", "belief": "b", "requirement": "r"}
TRUST = ("high", "medium", "low")
FIELDS = {
    "claim": ({"source", "quote", "says", "trust"}, {"why", "replaces"}),
    "belief": ({"statement", "why"}, {"from", "replaces"}),
    "requirement": ({"phrase"}, {"means", "open", "from", "why", "replaces"}),
}
MEANS = ("stat", "at_least", "deadline_turn", "avoid")


class RecordError(ValueError):
    """An invalid record; nothing in the batch is written."""


@dataclass
class Record:
    id: str
    type: str
    turn: int
    fields: dict            # the agent's fields, as given (validated)
    replaced_by: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "turn": self.turn, "fields": self.fields, "replaced_by": self.replaced_by}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Record":
        return cls(data["id"], data["type"], data["turn"], dict(data["fields"]), data["replaced_by"])

    @property
    def is_open(self) -> bool:
        """A requirement with an open question that has not been replaced."""
        return self.type == "requirement" and bool(self.fields.get("open")) and self.replaced_by is None

    def plants(self) -> set[str]:
        """Every plant the record mentions (as a key or a value anywhere in its fields)."""
        return _plants_in(self.fields)


def _plants_in(value) -> set[str]:
    if isinstance(value, str):
        return {value} if value in PLANTS else set()
    if isinstance(value, Mapping):
        return set().union(*(_plants_in(k) | _plants_in(v) for k, v in value.items())) if value else set()
    if isinstance(value, list):
        return set().union(*(_plants_in(v) for v in value)) if value else set()
    return set()


def _text(r: Mapping, key: str, required: bool = True) -> None:
    value = r.get(key)
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        raise RecordError(f'"{key}" must be a non-empty text.')


def _statement(value, key: str) -> None:
    try:
        check(value, [], [])
    except ValueError as err:
        raise RecordError(f'"{key}": {err}') from None


def _means(value) -> None:
    if not isinstance(value, dict):
        raise RecordError('"means" must be an object with any of: ' + ", ".join(MEANS) + ".")
    if extra := sorted(set(value) - set(MEANS)):
        raise RecordError(f'Unknown field "{extra[0]}" in "means" (allowed: {", ".join(MEANS)}).')
    if "stat" in value and value["stat"] not in STAT_SETS:
        raise RecordError('"stat" must be one of: ' + ", ".join(STAT_SETS) + ".")
    for key in ("at_least", "deadline_turn"):
        if key in value and (isinstance(value[key], bool) or not isinstance(value[key], int) or value[key] < 1):
            raise RecordError(f'"{key}" must be a whole number >= 1.')
    if "avoid" in value:
        avoid = value["avoid"]
        if not isinstance(avoid, list) or not all(p in PLANTS for p in avoid):
            raise RecordError('"avoid" must be a list of plant names.')


@dataclass
class RecordBook:
    records: list[Record] = field(default_factory=list)

    def to_dict(self) -> list[dict]:
        return [r.to_dict() for r in self.records]

    @classmethod
    def from_dict(cls, data: Iterable[Mapping]) -> "RecordBook":
        return cls([Record.from_dict(r) for r in data])

    def get(self, rid: str) -> Record | None:
        return next((r for r in self.records if r.id == rid), None)

    def add(self, batch: Sequence[Mapping], turn: int) -> list[Record]:
        """Validate the whole batch (later records may refer to earlier ones), then write it."""
        if not isinstance(batch, list) or not batch:
            raise RecordError('"records" must be a non-empty list of records.')
        staged: list[Record] = []
        counts = {t: sum(r.type == t for r in self.records) for t in TYPES}
        for i, raw in enumerate(batch, start=1):
            try:
                record = self._validate(raw, staged, counts, turn)
            except RecordError as err:
                raise RecordError(f"Record {i}: {err}" if len(batch) > 1 else str(err)) from None
            staged.append(record)
        for record in staged:
            if old := record.fields.get("replaces"):
                (self.get(old) or next(r for r in staged if r.id == old)).replaced_by = record.id
            self.records.append(record)
        return staged

    def _validate(self, raw, staged: list[Record], counts: dict[str, int], turn: int) -> Record:
        if not isinstance(raw, Mapping):
            raise RecordError("A record must be an object.")
        kind = raw.get("type")
        if kind not in TYPES:
            raise RecordError('"type" must be one of: ' + ", ".join(TYPES) + ".")
        required, optional = FIELDS[kind]
        if missing := sorted(required - set(raw)):
            raise RecordError(f'A {kind} needs "{missing[0]}".')
        if extra := sorted(set(raw) - required - optional - {"type"}):
            raise RecordError(f'Unknown field "{extra[0]}" for a {kind}.')
        known = {r.id: r for r in self.records + staged}

        if kind == "claim":
            _text(raw, "source")
            _text(raw, "quote")
            if raw["trust"] not in TRUST:
                raise RecordError('"trust" must be one of: ' + ", ".join(TRUST) + ".")
            says = raw["says"]
            if isinstance(says, Mapping) and "name" in says:
                if set(says) != {"name", "plant"} or not isinstance(says["name"], str) or not says["name"].strip():
                    raise RecordError('A name claim is {"name": "<what the source calls it>", "plant": "<plant>"}.')
                if says["plant"] not in PLANTS:
                    raise RecordError(f"Unknown plant {says['plant']}.")
            else:
                _statement(says, "says")
        elif kind == "belief":
            _statement(raw["statement"], "statement")
        else:
            _text(raw, "phrase")
            _means(raw.get("means", {}))
            _text(raw, "open", required=False)
            if not raw.get("means") and not raw.get("open"):
                raise RecordError('A requirement needs "means", an "open" question, or both.')
        _text(raw, "why", required=kind == "belief")

        sources = raw.get("from", [])
        if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
            raise RecordError('"from" must be a list of claim ids.')
        for sid in sources:
            if sid not in known or known[sid].type != "claim":
                raise RecordError(f"Unknown claim {sid}.")
        if "replaces" in raw:
            old = known.get(raw["replaces"])
            if old is None or old.type != kind:
                raise RecordError(f"{raw['replaces']} is not a {kind} that can be replaced.")
            if old.replaced_by is not None or any(r.fields.get("replaces") == old.id for r in staged):
                raise RecordError(f"{old.id} was already replaced.")

        counts[kind] += 1
        fields = {k: v for k, v in raw.items() if k != "type"}
        return Record(f"{TYPES[kind]}{counts[kind]}", kind, turn, fields)
