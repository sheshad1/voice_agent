"""Local Do-Not-Disturb list, checked before every outbound dial."""

from datetime import datetime

from rider_agent.db import Database
from rider_agent.models import normalize_phone
from rider_agent.timeutil import to_iso, utcnow


def add_to_dnd(db: Database, phone: str, now: datetime | None = None) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dnd (phone, added_at) VALUES (?, ?)",
            (normalize_phone(phone), to_iso(now or utcnow())),
        )


def is_dnd(db: Database, phone: str) -> bool:
    with db.connect() as conn:
        row = conn.execute("SELECT 1 FROM dnd WHERE phone = ?", (normalize_phone(phone),)).fetchone()
    return row is not None
