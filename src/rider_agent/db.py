"""SQLite storage. One short-lived connection per unit of work."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    city TEXT,
    language TEXT NOT NULL DEFAULT 'Hindi',
    source TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'new',
    unanswered_attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id),
    status TEXT NOT NULL,
    interaction_id TEXT,
    duration REAL,
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    centre TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    booked INTEGER NOT NULL DEFAULT 0,
    UNIQUE (centre, starts_at)
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id TEXT NOT NULL UNIQUE,
    slot_id INTEGER NOT NULL REFERENCES slots(id),
    name TEXT,
    phone TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
    interaction_id TEXT PRIMARY KEY,
    lead_id INTEGER,
    attempt_id TEXT,
    phone TEXT,
    name TEXT,
    city TEXT,
    language TEXT,
    intent TEXT,
    has_vehicle INTEGER,
    docs_ready INTEGER,
    outcome TEXT NOT NULL,
    reason TEXT,
    agent_outcome TEXT,
    matches_agent INTEGER,
    slot_id INTEGER,
    callback_window TEXT,
    transcript TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dnd (
    phone TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yields a connection that commits on success and rolls back on error."""
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
