"""SQLite cache of the timetable, so the API answers even when EduPage is down."""

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    date     TEXT    NOT NULL,
    position INTEGER NOT NULL,
    data     TEXT    NOT NULL,
    PRIMARY KEY (date, position)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = data_dir / "timetable.db"
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # One short-lived connection per call: the sync runs in a worker thread
        # while the API reads from the event loop thread.
        return sqlite3.connect(self.path)

    def replace_day(self, day: date, lessons: list[dict]) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM lessons WHERE date = ?", (day.isoformat(),))
            db.executemany(
                "INSERT INTO lessons (date, position, data) VALUES (?, ?, ?)",
                [
                    (day.isoformat(), i, json.dumps(lesson, ensure_ascii=False))
                    for i, lesson in enumerate(lessons)
                ],
            )

    def lessons_between(self, date_from: date, date_to: date) -> list[dict]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT position, data FROM lessons WHERE date BETWEEN ? AND ? "
                "ORDER BY date, position",
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()
        return [{**json.loads(data), "position": position} for position, data in rows]

    def set_meta(self, key: str, value) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def get_meta(self, key: str, default=None):
        with closing(self._connect()) as db:
            row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default
