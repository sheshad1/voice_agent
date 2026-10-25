"""Call-attempt bookkeeping and the Sarvam call-status webhook."""

from datetime import datetime
from typing import Any

from rider_agent import crm, leads
from rider_agent.config import Settings
from rider_agent.db import Database
from rider_agent.errors import UnknownAttemptError
from rider_agent.models import CallStatus, CallStatusPayload, OutcomeRequest
from rider_agent.timeutil import to_iso, utcnow


def record_attempt(db: Database, lead_id: int, attempt_id: str, now: datetime) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO attempts (attempt_id, lead_id, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            (attempt_id, lead_id, CallStatus.INITIATED.value, to_iso(now)),
        )


def handle_call_status(
    db: Database,
    settings: Settings,
    payload: CallStatusPayload,
    now: datetime | None = None,
) -> str:
    """Reconciles a call-attempt result with its lead.

    Returns:
        "duplicate" when the attempt was already finalised, else "processed".

    Raises:
        UnknownAttemptError: If the attempt cannot be tied to a lead.
    """
    now = now or utcnow()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT lead_id, status FROM attempts WHERE attempt_id = ?", (payload.attempt_id,)
        ).fetchone()
    lead_id = row["lead_id"] if row else payload.metadata_lead_id()
    if lead_id is None:
        raise UnknownAttemptError(payload.attempt_id)
    if row and row["status"] != CallStatus.INITIATED.value:
        return "duplicate"

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO attempts (attempt_id, lead_id, status, interaction_id, duration, "
            "failure_reason, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(attempt_id) DO UPDATE SET status = excluded.status, "
            "interaction_id = excluded.interaction_id, duration = excluded.duration, "
            "failure_reason = excluded.failure_reason, completed_at = excluded.completed_at",
            (
                payload.attempt_id,
                lead_id,
                payload.status.value,
                payload.interaction_id,
                payload.duration,
                payload.failure_reason,
                to_iso(now),
                to_iso(now),
            ),
        )

    if payload.status is CallStatus.CONNECTED and payload.interaction_id:
        crm.record_outcome(db, settings, _outcome_from_webhook(payload, lead_id), now)
    else:
        leads.schedule_retry(db, lead_id, settings, now)
    return "processed"


def _outcome_from_webhook(payload: CallStatusPayload, lead_id: int) -> OutcomeRequest:
    variables: dict[str, Any] = dict(payload.final_agent_variables or {})
    variables.update(
        interaction_id=payload.interaction_id,
        attempt_id=payload.attempt_id,
        lead_id=lead_id,
        transcript=crm.serialize_transcript(payload.interaction_transcript),
    )
    return OutcomeRequest.model_validate(variables)
