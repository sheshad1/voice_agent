"""Lead scheduler: dials due leads inside working hours."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from rider_agent import calls, dnd, leads
from rider_agent.config import Settings
from rider_agent.db import Database
from rider_agent.errors import DialerError
from rider_agent.models import Lead
from rider_agent.schedule import in_working_hours
from rider_agent.timeutil import utcnow


class Dialer(Protocol):
    def place_call(self, lead: Lead) -> str: ...


@dataclass(frozen=True)
class DialResult:
    lead_id: int
    attempt_id: str | None
    error: str | None = None


def run_once(
    db: Database,
    dialer: Dialer,
    settings: Settings,
    now: datetime | None = None,
) -> list[DialResult]:
    """Runs one scheduling pass and returns what was dialed.

    Nothing is dialed outside working hours or beyond the concurrency limit,
    and numbers on the DND list are never called.
    """
    now = now or utcnow()
    leads.release_stale_dialing(db, settings, now)
    if not in_working_hours(now, settings):
        return []

    capacity = settings.max_concurrency - leads.count_dialing(db)
    if capacity <= 0:
        return []

    results: list[DialResult] = []
    for lead in leads.due_leads(db, now, capacity):
        if dnd.is_dnd(db, lead.phone):
            leads.mark_dnd(db, lead.id, now)
            continue
        try:
            attempt_id = dialer.place_call(lead)
        except DialerError as exc:
            leads.schedule_retry(db, lead.id, settings, now)
            results.append(DialResult(lead.id, None, str(exc)))
            continue
        calls.record_attempt(db, lead.id, attempt_id, now)
        leads.mark_dialing(db, lead.id, now)
        results.append(DialResult(lead.id, attempt_id))
    return results
