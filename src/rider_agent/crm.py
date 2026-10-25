"""CRM outcome recording: the target of the agent's on_end push."""

import json
from datetime import datetime

from rider_agent import booking, dnd, leads, qualification
from rider_agent.config import Settings
from rider_agent.db import Database
from rider_agent.models import Intent, Lead, Outcome, OutcomeRecord, OutcomeRequest
from rider_agent.timeutil import to_iso, utcnow


def _resolve_lead(db: Database, request: OutcomeRequest) -> Lead | None:
    if request.lead_id is not None:
        return leads.get_lead(db, request.lead_id)
    if request.phone:
        try:
            return leads.find_by_phone(db, request.phone)
        except ValueError:
            return None
    return None


def record_outcome(
    db: Database,
    settings: Settings,
    request: OutcomeRequest,
    now: datetime | None = None,
) -> OutcomeRecord:
    """Stores the call outcome, upserting by `interaction_id`.

    The verdict is recomputed from the captured answers and the booking table;
    the agent's own claim is kept only to measure how often it agrees.
    Lead lifecycle moves once per interaction, so duplicate pushes are safe.
    """
    now = now or utcnow()
    stamp = to_iso(now)
    lead = _resolve_lead(db, request)
    decision = qualification.evaluate(request, booked=booking.has_booking(db, request.interaction_id))
    matches = (
        None
        if request.outcome is None
        else request.outcome.strip().casefold() == decision.outcome.value
    )
    city = request.city or (lead.city if lead else None)

    with db.connect() as conn:
        first_seen = (
            conn.execute(
                "SELECT 1 FROM outcomes WHERE interaction_id = ?", (request.interaction_id,)
            ).fetchone()
            is None
        )
        conn.execute(
            "INSERT INTO outcomes (interaction_id, lead_id, attempt_id, phone, name, city, language, "
            "intent, has_vehicle, docs_ready, outcome, reason, agent_outcome, matches_agent, slot_id, "
            "callback_window, transcript, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(interaction_id) DO UPDATE SET "
            "lead_id = excluded.lead_id, attempt_id = COALESCE(excluded.attempt_id, attempt_id), "
            "phone = excluded.phone, name = excluded.name, city = excluded.city, "
            "language = excluded.language, intent = excluded.intent, "
            "has_vehicle = excluded.has_vehicle, docs_ready = excluded.docs_ready, "
            "outcome = excluded.outcome, reason = excluded.reason, "
            "agent_outcome = excluded.agent_outcome, matches_agent = excluded.matches_agent, "
            "slot_id = excluded.slot_id, callback_window = excluded.callback_window, "
            "transcript = COALESCE(excluded.transcript, transcript), updated_at = excluded.updated_at",
            (
                request.interaction_id,
                lead.id if lead else None,
                request.attempt_id,
                request.phone or (lead.phone if lead else None),
                request.name or (lead.name if lead else None),
                city,
                request.language or (lead.language.value if lead else None),
                request.intent.value if request.intent else None,
                request.has_vehicle,
                request.docs_ready,
                decision.outcome.value,
                decision.reason.value if decision.reason else None,
                request.outcome,
                matches,
                request.slot_id,
                request.callback_window.value if request.callback_window else None,
                request.transcript,
                stamp,
                stamp,
            ),
        )

    if lead:
        _apply_lifecycle(db, settings, lead, request, decision.outcome, first_seen, now)

    return OutcomeRecord(
        interaction_id=request.interaction_id,
        outcome=decision.outcome,
        reason=decision.reason,
        matches_agent=matches,
        lead_id=lead.id if lead else None,
    )


def _apply_lifecycle(
    db: Database,
    settings: Settings,
    lead: Lead,
    request: OutcomeRequest,
    outcome: Outcome,
    first_seen: bool,
    now: datetime,
) -> None:
    if request.do_not_call:
        dnd.add_to_dnd(db, lead.phone, now)
        leads.mark_dnd(db, lead.id, now)
        return
    if not first_seen:
        return
    if request.intent is Intent.CALL_BACK_LATER:
        leads.schedule_callback(db, lead.id, request.callback_window, settings, now)
    elif outcome is Outcome.FOLLOW_UP_NEEDED:
        leads.schedule_retry(db, lead.id, settings, now)
    else:
        leads.mark_completed(db, lead.id, now)


def serialize_transcript(turns: list[dict] | None) -> str | None:
    return json.dumps(turns, ensure_ascii=False) if turns else None
