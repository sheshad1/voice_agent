from datetime import timedelta

import pytest

from rider_agent import booking, calls, crm, dnd, leads, scheduler
from rider_agent.errors import DialerError, UnknownAttemptError
from rider_agent.models import (
    BookingRequest,
    CallStatusPayload,
    Language,
    LeadStatus,
    Outcome,
    OutcomeRequest,
)


class FakeDialer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.dialed: list[int] = []

    def place_call(self, lead) -> str:
        if self.fail:
            raise DialerError("boom")
        self.dialed.append(lead.id)
        return f"attempt-{lead.id}"


@pytest.fixture
def lead(db, now):
    created, _ = leads.add_lead(db, "Asha", "9876543210", "Bengaluru", Language.HINDI, now=now)
    return created


def outcome_request(lead_id: int, **kwargs) -> OutcomeRequest:
    base = {
        "interaction_id": "call-1",
        "lead_id": lead_id,
        "intent": "interested",
        "has_vehicle": "yes",
        "docs_ready": "yes",
        "city": "Bengaluru",
    }
    return OutcomeRequest.model_validate({**base, **kwargs})


def status_of(db, lead_id: int) -> LeadStatus:
    return leads.get_lead(db, lead_id).status


class TestScheduler:
    def test_dials_due_lead_within_hours(self, db, settings, lead, now):
        dialer = FakeDialer()
        results = scheduler.run_once(db, dialer, settings, now)
        assert [r.lead_id for r in results] == [lead.id]
        assert status_of(db, lead.id) is LeadStatus.DIALING

    def test_does_not_dial_outside_working_hours(self, db, settings, lead, now):
        night = now + timedelta(hours=11)
        assert scheduler.run_once(db, FakeDialer(), settings, night) == []
        assert status_of(db, lead.id) is LeadStatus.NEW

    def test_skips_and_flags_dnd_numbers(self, db, settings, lead, now):
        dnd.add_to_dnd(db, lead.phone, now)
        dialer = FakeDialer()
        assert scheduler.run_once(db, dialer, settings, now) == []
        assert dialer.dialed == []
        assert status_of(db, lead.id) is LeadStatus.DND

    def test_respects_concurrency_limit(self, db, settings, now):
        for i in range(4):
            leads.add_lead(db, f"L{i}", f"98765432{i:02d}", "Pune", now=now)
        settings.max_concurrency = 2
        assert len(scheduler.run_once(db, FakeDialer(), settings, now)) == 2
        assert scheduler.run_once(db, FakeDialer(), settings, now) == []

    def test_dial_failure_schedules_retry(self, db, settings, lead, now):
        results = scheduler.run_once(db, FakeDialer(fail=True), settings, now)
        assert results[0].error
        assert status_of(db, lead.id) is LeadStatus.RETRY

    def test_stale_dialing_lead_is_requeued(self, db, settings, lead, now):
        scheduler.run_once(db, FakeDialer(), settings, now)
        later = now + timedelta(minutes=settings.stale_dialing_minutes + 1)
        assert leads.release_stale_dialing(db, settings, later) == 1
        assert status_of(db, lead.id) is LeadStatus.RETRY


class TestCallStatusWebhook:
    def payload(self, status: str, **kwargs) -> CallStatusPayload:
        return CallStatusPayload.model_validate({"attempt_id": "a1", "status": status, **kwargs})

    def test_no_answer_retries_then_exhausts(self, db, settings, lead, now):
        calls.record_attempt(db, lead.id, "a1", now)
        calls.handle_call_status(db, settings, self.payload("no_answer"), now)
        assert status_of(db, lead.id) is LeadStatus.RETRY
        assert leads.get_lead(db, lead.id).next_attempt_at > now

        for n in (2, 3):
            calls.record_attempt(db, lead.id, f"a{n}", now)
            payload = CallStatusPayload(attempt_id=f"a{n}", status="busy")
            calls.handle_call_status(db, settings, payload, now)
        assert status_of(db, lead.id) is LeadStatus.EXHAUSTED

    def test_duplicate_delivery_is_ignored(self, db, settings, lead, now):
        calls.record_attempt(db, lead.id, "a1", now)
        calls.handle_call_status(db, settings, self.payload("failed"), now)
        assert calls.handle_call_status(db, settings, self.payload("failed"), now) == "duplicate"
        assert leads.get_lead(db, lead.id).unanswered_attempts == 1

    def test_unknown_attempt_without_metadata_raises(self, db, settings, now):
        with pytest.raises(UnknownAttemptError):
            calls.handle_call_status(db, settings, self.payload("failed"), now)

    def test_unknown_attempt_is_recovered_from_metadata(self, db, settings, lead, now):
        payload = self.payload("no_answer", webhook_config={"metadata": {"lead_id": lead.id}})
        assert calls.handle_call_status(db, settings, payload, now) == "processed"
        assert status_of(db, lead.id) is LeadStatus.RETRY

    def test_connected_call_records_outcome_when_on_end_push_missed(self, db, settings, lead, now):
        calls.record_attempt(db, lead.id, "a1", now)
        payload = self.payload(
            "connected",
            interaction_id="call-9",
            final_agent_variables={"intent": "not_interested"},
            interaction_transcript=[{"role": "agent", "en_text": "Hello"}],
        )
        calls.handle_call_status(db, settings, payload, now)
        with db.connect() as conn:
            row = conn.execute("SELECT outcome, transcript FROM outcomes").fetchone()
        assert row["outcome"] == Outcome.NOT_INTERESTED.value
        assert "Hello" in row["transcript"]
        assert status_of(db, lead.id) is LeadStatus.COMPLETED


class TestCrmLifecycle:
    def test_booked_call_completes_lead(self, db, settings, lead, now):
        booking.seed_slots(db, settings, now=now)
        slot = booking.list_open_slots(db, settings, "Bengaluru", now=now).slots[0]
        booking.book_slot(
            db,
            settings,
            BookingRequest.model_validate(
                {
                    "interaction_id": "call-1",
                    "slot_id": slot.slot_id,
                    "intent": "interested",
                    "has_vehicle": "yes",
                    "docs_ready": "yes",
                    "city": "Bengaluru",
                }
            ),
            now=now,
        )
        record = crm.record_outcome(db, settings, outcome_request(lead.id), now)
        assert record.outcome is Outcome.QUALIFIED_BOOKED
        assert status_of(db, lead.id) is LeadStatus.COMPLETED

    def test_agent_claiming_booked_without_booking_is_overruled(self, db, settings, lead, now):
        record = crm.record_outcome(
            db, settings, outcome_request(lead.id, outcome="qualified_booked"), now
        )
        assert record.outcome is Outcome.FOLLOW_UP_NEEDED
        assert record.matches_agent is False

    def test_callback_request_is_scheduled_in_requested_window(self, db, settings, lead, now):
        crm.record_outcome(
            db,
            settings,
            outcome_request(lead.id, intent="call_back_later", callback_window="evening"),
            now,
        )
        refreshed = leads.get_lead(db, lead.id)
        assert refreshed.status is LeadStatus.CALLBACK
        assert refreshed.next_attempt_at.astimezone(settings.tz).hour == 18

    def test_duplicate_push_does_not_double_count_attempts(self, db, settings, lead, now):
        request = outcome_request(lead.id, has_vehicle=None)
        crm.record_outcome(db, settings, request, now)
        crm.record_outcome(db, settings, request, now)
        assert leads.get_lead(db, lead.id).unanswered_attempts == 1

    def test_do_not_call_request_blocks_future_dials(self, db, settings, lead, now):
        crm.record_outcome(
            db, settings, outcome_request(lead.id, intent="not_interested", do_not_call="yes"), now
        )
        assert dnd.is_dnd(db, lead.phone)
        assert status_of(db, lead.id) is LeadStatus.DND

    def test_outcome_without_known_lead_is_still_stored(self, db, settings, now):
        record = crm.record_outcome(
            db, settings, OutcomeRequest(interaction_id="orphan", intent="not_interested"), now
        )
        assert record.lead_id is None
        assert record.outcome is Outcome.NOT_INTERESTED
