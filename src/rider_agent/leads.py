"""Lead storage and lifecycle transitions."""

from datetime import datetime, timedelta

from rider_agent.config import Settings
from rider_agent.db import Database
from rider_agent.models import CallbackWindow, Language, Lead, LeadStatus, normalize_phone
from rider_agent.schedule import callback_time, clamp_to_window
from rider_agent.timeutil import from_iso, to_iso, utcnow

_DUE_STATUSES = (LeadStatus.NEW, LeadStatus.RETRY, LeadStatus.CALLBACK)


def _to_lead(row) -> Lead:
    next_at = row["next_attempt_at"]
    return Lead(
        id=row["id"],
        name=row["name"],
        phone=row["phone"],
        city=row["city"],
        language=Language(row["language"]),
        source=row["source"],
        status=LeadStatus(row["status"]),
        unanswered_attempts=row["unanswered_attempts"],
        next_attempt_at=from_iso(next_at) if next_at else None,
        created_at=from_iso(row["created_at"]),
    )


def add_lead(
    db: Database,
    name: str,
    phone: str,
    city: str | None,
    language: Language = Language.HINDI,
    source: str = "manual",
    now: datetime | None = None,
) -> tuple[Lead, bool]:
    """Inserts a lead keyed by phone number.

    Returns:
        The lead and whether it was newly created (False for a duplicate phone).
    """
    stamp = to_iso(now or utcnow())
    normalized = normalize_phone(phone)
    with db.connect() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO leads "
            "(name, phone, city, language, source, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, normalized, city, language.value, source, LeadStatus.NEW.value, stamp, stamp),
        )
        row = conn.execute("SELECT * FROM leads WHERE phone = ?", (normalized,)).fetchone()
    return _to_lead(row), cursor.rowcount == 1


def get_lead(db: Database, lead_id: int) -> Lead | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return _to_lead(row) if row else None


def find_by_phone(db: Database, phone: str) -> Lead | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE phone = ?", (normalize_phone(phone),)).fetchone()
    return _to_lead(row) if row else None


def due_leads(db: Database, now: datetime, limit: int) -> list[Lead]:
    placeholders = ",".join("?" * len(_DUE_STATUSES))
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM leads WHERE status IN ({placeholders}) "
            "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
            "ORDER BY COALESCE(next_attempt_at, created_at), id LIMIT ?",
            (*[s.value for s in _DUE_STATUSES], to_iso(now), limit),
        ).fetchall()
    return [_to_lead(row) for row in rows]


def count_dialing(db: Database) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE status = ?", (LeadStatus.DIALING.value,)
        ).fetchone()
    return row["n"]


def _update(
    db: Database,
    lead_id: int,
    status: LeadStatus,
    now: datetime,
    next_attempt_at: datetime | None = None,
    unanswered_attempts: int | None = None,
) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE leads SET status = ?, next_attempt_at = ?, updated_at = ?, "
            "unanswered_attempts = COALESCE(?, unanswered_attempts) WHERE id = ?",
            (
                status.value,
                to_iso(next_attempt_at) if next_attempt_at else None,
                to_iso(now),
                unanswered_attempts,
                lead_id,
            ),
        )


def mark_dialing(db: Database, lead_id: int, now: datetime) -> None:
    _update(db, lead_id, LeadStatus.DIALING, now)


def mark_completed(db: Database, lead_id: int, now: datetime) -> None:
    _update(db, lead_id, LeadStatus.COMPLETED, now, unanswered_attempts=0)


def mark_dnd(db: Database, lead_id: int, now: datetime) -> None:
    _update(db, lead_id, LeadStatus.DND, now)


def schedule_retry(db: Database, lead_id: int, settings: Settings, now: datetime) -> LeadStatus:
    """Counts a failed or incomplete attempt, then retries later or gives up."""
    lead = get_lead(db, lead_id)
    if lead is None:
        raise LookupError(f"Unknown lead {lead_id}")
    attempts = lead.unanswered_attempts + 1
    if attempts >= settings.max_unanswered_attempts:
        _update(db, lead_id, LeadStatus.EXHAUSTED, now, unanswered_attempts=attempts)
        return LeadStatus.EXHAUSTED
    retry_at = clamp_to_window(now + timedelta(minutes=settings.retry_backoff_minutes), settings)
    _update(db, lead_id, LeadStatus.RETRY, now, retry_at, attempts)
    return LeadStatus.RETRY


def schedule_callback(
    db: Database,
    lead_id: int,
    window: CallbackWindow | None,
    settings: Settings,
    now: datetime,
) -> None:
    _update(
        db,
        lead_id,
        LeadStatus.CALLBACK,
        now,
        callback_time(window, settings, now),
        unanswered_attempts=0,
    )


def release_stale_dialing(db: Database, settings: Settings, now: datetime) -> int:
    """Re-queues leads whose call-status webhook never arrived."""
    cutoff = to_iso(now - timedelta(minutes=settings.stale_dialing_minutes))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM leads WHERE status = ? AND updated_at <= ?",
            (LeadStatus.DIALING.value, cutoff),
        ).fetchall()
    for row in rows:
        schedule_retry(db, row["id"], settings, now)
    return len(rows)


def status_counts(db: Database) -> dict[str, int]:
    with db.connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
    return {row["status"]: row["n"] for row in rows}
