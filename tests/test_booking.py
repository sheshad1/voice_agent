from datetime import timedelta

import pytest

from rider_agent import booking
from rider_agent.models import BookingRequest


def request(slot_id: int, **kwargs) -> BookingRequest:
    base = {
        "interaction_id": "call-1",
        "slot_id": slot_id,
        "intent": "interested",
        "has_vehicle": "yes",
        "docs_ready": "yes",
        "city": "Bengaluru",
        "name": "Asha",
        "phone": "+919876543210",
    }
    return BookingRequest.model_validate({**base, **kwargs})


@pytest.fixture
def seeded(db, settings, now):
    booking.seed_slots(db, settings, now=now)
    return db


def test_seed_is_idempotent(seeded, settings, now):
    assert booking.seed_slots(seeded, settings, now=now) == 0


def test_lists_future_slots_for_city_alias(seeded, settings, now):
    response = booking.list_open_slots(seeded, settings, "Bangalore", now=now)
    assert response.serviceable
    assert response.city == "Bengaluru"
    assert len(response.slots) == 3
    assert all(slot.starts_at > now for slot in response.slots)
    assert "Koramangala" in response.slots[0].spoken


def test_unserved_city_has_no_slots(seeded, settings, now):
    response = booking.list_open_slots(seeded, settings, "Jaipur", now=now)
    assert not response.serviceable
    assert response.slots == []


def test_booking_succeeds_and_is_idempotent(seeded, settings, now):
    slot = booking.list_open_slots(seeded, settings, "Bengaluru", now=now).slots[0]
    first = booking.book_slot(seeded, settings, request(slot.slot_id), now=now)
    again = booking.book_slot(seeded, settings, request(slot.slot_id), now=now)
    assert first.booked and again.booked
    assert first.booking_id == again.booking_id
    with seeded.connect() as conn:
        assert conn.execute("SELECT booked FROM slots WHERE id = ?", (slot.slot_id,)).fetchone()[0] == 1


@pytest.mark.parametrize("overrides", [{"has_vehicle": "no"}, {"intent": "not_interested"}])
def test_unqualified_lead_cannot_book(seeded, settings, now, overrides):
    slot = booking.list_open_slots(seeded, settings, "Bengaluru", now=now).slots[0]
    result = booking.book_slot(seeded, settings, request(slot.slot_id, **overrides), now=now)
    assert not result.booked
    assert not booking.has_booking(seeded, "call-1")


def test_lead_without_documents_can_still_book(seeded, settings, now):
    slot = booking.list_open_slots(seeded, settings, "Bengaluru", now=now).slots[0]
    result = booking.book_slot(seeded, settings, request(slot.slot_id, docs_ready="no"), now=now)
    assert result.booked


def test_slot_in_other_city_is_rejected(seeded, settings, now):
    pune = booking.list_open_slots(seeded, settings, "Pune", now=now).slots[0]
    result = booking.book_slot(seeded, settings, request(pune.slot_id), now=now)
    assert not result.booked


def test_full_slot_is_rejected(seeded, settings, now):
    slot = booking.list_open_slots(seeded, settings, "Bengaluru", now=now).slots[0]
    with seeded.connect() as conn:
        conn.execute("UPDATE slots SET capacity = 1, booked = 1 WHERE id = ?", (slot.slot_id,))
    result = booking.book_slot(seeded, settings, request(slot.slot_id), now=now)
    assert not result.booked
    assert "taken" in result.message


def test_past_slot_is_rejected(seeded, settings, now):
    slot = booking.list_open_slots(seeded, settings, "Bengaluru", now=now).slots[0]
    late = slot.starts_at + timedelta(hours=1)
    assert not booking.book_slot(seeded, settings, request(slot.slot_id), now=late).booked
