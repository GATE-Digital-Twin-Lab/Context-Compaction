"""Knowledge base (SQLite): growth times, current plantings, outcome statements."""

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from environment.brewer import Effect
from environment.garden import GardenState

LABELS = ("odd", "even", "higher", "lower", "present")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plants   (plant TEXT PRIMARY KEY, turns INTEGER);
CREATE TABLE IF NOT EXISTS plantings(plot INTEGER PRIMARY KEY, plant TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT UNIQUE NOT NULL,
    effect TEXT NOT NULL,
    potion_id INTEGER,
    turn INTEGER
);
CREATE TABLE IF NOT EXISTS outcome_plants(
    outcome_id INTEGER NOT NULL REFERENCES outcomes(id),
    plant TEXT NOT NULL,
    label TEXT NOT NULL
);
"""


class LogError(ValueError):
    """Invalid log entry (e.g. a label outside the vocabulary)."""


def effect_label(effect: Effect) -> str:
    """'+S', '-S' or 'none'."""
    if effect.positive:
        return "+" + next(iter(effect.positive))
    if effect.negative:
        return "-" + next(iter(effect.negative))
    return "none"


@dataclass(frozen=True)
class Outcome:
    labels: dict[str, str]  # plant -> label, sorted by plant
    effect: str

    def render(self) -> str:
        """E.g. '(higher) p2, p4, odd p6 → +I'."""
        parts = []
        for plant, label in self.labels.items():
            if label in ("higher", "lower", 'odd', "even"):
                parts.append(f"({label}) {plant}")
            else:
                parts.append(plant)
        return f"{', '.join(parts)} → {self.effect}"


@dataclass(frozen=True)
class GardenLogResult:
    growth: dict[str, int]    # newly logged growth times
    plantings: dict[int, str] # newly logged plantings


class KnowledgeBase:
    def __init__(self, path: str = ":memory:", catalogue: Iterable[tuple[str, int | None]] = ()) -> None:
        self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)
        self._db.executemany("INSERT OR IGNORE INTO plants VALUES (?, ?)", catalogue)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # --- reads -------------------------------------------------------------

    def catalogue(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT plant FROM plants ORDER BY plant")]

    def growth_times(self) -> dict[str, int]:
        """Logged growth times only (plants with unknown growth are left out)."""
        return dict(
            self._db.execute("SELECT plant, turns FROM plants WHERE turns IS NOT NULL ORDER BY plant")
        )

    def plantings(self) -> dict[int, str]:
        return dict(self._db.execute("SELECT plot, plant FROM plantings ORDER BY plot"))

    def outcomes(self, plant: str | None = None) -> list[Outcome]:
        """Outcome statements in logging order, optionally only those involving a plant."""
        query = "SELECT id, effect FROM outcomes"
        args: tuple = ()
        if plant is not None:
            query += " WHERE id IN (SELECT outcome_id FROM outcome_plants WHERE plant = ?)"
            args = (plant,)
        result = []
        for oid, effect in self._db.execute(query + " ORDER BY id", args).fetchall():
            rows = self._db.execute(
                "SELECT plant, label FROM outcome_plants WHERE outcome_id = ? ORDER BY plant",
                (oid,),
            )
            result.append(Outcome(dict(rows), effect))
        return result

    # --- writes ------------------------------------------------------------

    def log_garden(self, state: GardenState, growth_times: Mapping[str, int]) -> GardenLogResult:
        """Log growth times of ready plants and plantings of all occupied plots (new ones only)."""
        known_growth = self.growth_times()
        known_plantings = self.plantings()
        new_growth = {
            r.plant: growth_times[r.plant]
            for r in state.ready
            if known_growth.get(r.plant) is None
        }
        occupied = [(r.plot, r.plant) for r in state.ready] + [(g.plot, g.plant) for g in state.growing]
        new_plantings = {plot: plant for plot, plant in sorted(occupied) if plot not in known_plantings}
        self._db.executemany(
            "UPDATE plants SET turns = ? WHERE plant = ?",
            [(turns, plant) for plant, turns in sorted(new_growth.items())],
        )
        self._db.executemany("INSERT INTO plantings VALUES (?, ?)", new_plantings.items())
        self._db.commit()
        return GardenLogResult(dict(sorted(new_growth.items())), new_plantings)

    def clear_plantings(self, plots: Iterable[int]) -> None:
        """Remove planting records of gathered plots."""
        self._db.executemany("DELETE FROM plantings WHERE plot = ?", [(p,) for p in plots])
        self._db.commit()

    def log_outcome(
        self, labels: Mapping[str, str], effect: str, potion_id: int, turn: int
    ) -> bool:
        """Append an outcome statement; return False if it is an exact duplicate."""
        bad = sorted(set(labels.values()) - set(LABELS))
        if bad:
            raise LogError(f'Invalid label "{bad[0]}" (allowed: {", ".join(LABELS)}).')
        ordered = dict(sorted(labels.items()))
        signature = effect + "|" + ",".join(f"{p}:{l}" for p, l in ordered.items())
        cur = self._db.execute(
            "INSERT OR IGNORE INTO outcomes (signature, effect, potion_id, turn) VALUES (?, ?, ?, ?)",
            (signature, effect, potion_id, turn),
        )
        if cur.rowcount == 0:
            return False
        self._db.executemany(
            "INSERT INTO outcome_plants VALUES (?, ?, ?)",
            [(cur.lastrowid, p, l) for p, l in ordered.items()],
        )
        self._db.commit()
        return True
