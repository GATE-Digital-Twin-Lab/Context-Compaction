"""Knowledge base (SQLite): plant catalogue, outcome statements, lore. (Garden logging is gone: growth
records are automatic, see Garden.growth_records.)"""

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from environment.brewer import Effect

LABELS = ("odd", "even", "higher", "lower", "present")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plants   (plant TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT UNIQUE NOT NULL,
    effect TEXT NOT NULL,
    potion_id INTEGER,
    turn INTEGER
);
CREATE TABLE IF NOT EXISTS lore(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_a TEXT NOT NULL,
    plant_b TEXT NOT NULL,
    text TEXT NOT NULL,
    turn INTEGER,
    UNIQUE(plant_a, plant_b)
);
CREATE TABLE IF NOT EXISTS outcome_plants(
    outcome_id INTEGER NOT NULL REFERENCES outcomes(id),
    plant TEXT NOT NULL,
    label TEXT NOT NULL
);
"""


def _marks(values: tuple) -> str:
    return ", ".join("?" * len(values))


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
        """E.g. '(higher) elderberry, sage, odd dill → +I'."""
        parts = []
        for plant, label in self.labels.items():
            if label in ("higher", "lower", 'odd', "even"):
                parts.append(f"({label}) {plant}")
            else:
                parts.append(plant)
        return f"{', '.join(parts)} → {self.effect}"


class KnowledgeBase:
    def __init__(self, path: str = ":memory:", catalogue: Iterable[str] = ()) -> None:
        self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)
        self._db.executemany("INSERT OR IGNORE INTO plants VALUES (?)", [(p,) for p in catalogue])
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    _TABLES = ("plants", "outcomes", "outcome_plants", "lore")

    def dump(self) -> dict[str, list[list]]:
        """All rows of every table (for checkpoints)."""
        return {t: [list(r) for r in self._db.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in self._TABLES}

    def restore(self, data: Mapping[str, list[list]]) -> None:
        """Replace all contents with a dump, e.g. after a crash left the file ahead of the checkpoint."""
        with self._db:
            for table in reversed(self._TABLES):
                self._db.execute(f"DELETE FROM {table}")
            for table in self._TABLES:
                for row in data.get(table, []):  # checkpoints from before a table existed
                    self._db.execute(f"INSERT INTO {table} VALUES ({_marks(row)})", row)

    # --- reads -------------------------------------------------------------

    def catalogue(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT plant FROM plants ORDER BY plant")]

    def outcomes(self, *plants: str) -> list[Outcome]:
        """Outcome statements in logging order, optionally only those involving any of some plants."""
        query = "SELECT id, effect FROM outcomes"
        if plants:
            query += f" WHERE id IN (SELECT outcome_id FROM outcome_plants WHERE plant IN ({_marks(plants)}))"
        result = []
        for oid, effect in self._db.execute(query + " ORDER BY id", plants).fetchall():
            rows = self._db.execute(
                "SELECT plant, label FROM outcome_plants WHERE outcome_id = ? ORDER BY plant",
                (oid,),
            )
            result.append(Outcome(dict(rows), effect))
        return result

    def lore(self, *plants: str) -> list[str]:
        """Unlocked lore lines in unlocking order, optionally only those naming any of some plants."""
        query = "SELECT text FROM lore"
        if plants:
            query += f" WHERE plant_a IN ({_marks(plants)}) OR plant_b IN ({_marks(plants)})"
        return [r[0] for r in self._db.execute(query + " ORDER BY id", plants * 2)]

    def lore_entries(self) -> list[tuple[str, str, str, int]]:
        """(plant_a, plant_b, text, turn unlocked) in unlocking order."""
        return [tuple(r) for r in self._db.execute("SELECT plant_a, plant_b, text, turn FROM lore ORDER BY id")]

    # --- writes ------------------------------------------------------------

    def unlock_lore(self, lines: Mapping[tuple[str, str], str], turn: int) -> list[tuple[str, str]]:
        """Store lore lines (pair -> text); return the pairs that were new."""
        new = []
        for (a, b), text in lines.items():
            cur = self._db.execute(
                "INSERT OR IGNORE INTO lore (plant_a, plant_b, text, turn) VALUES (?, ?, ?, ?)", (a, b, text, turn)
            )
            if cur.rowcount:
                new.append((a, b))
        self._db.commit()
        return new

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
