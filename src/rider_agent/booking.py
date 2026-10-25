"""Onboarding-slot inventory and booking."""

import sqlite3
from datetime import datetime, time, timedelta

from pydantic import BaseModel

from rider_agent import qualification
from rider_agent.cities import CENTRES, canonical_city
from rider_agent.config import Settings
from rider_agent.db import Database
from rider_agent.models import BookingRequest, SlotView
from rider_agent.timeutil import from_iso, to_iso, utcnow

SLOT_HOURS = (10, 14, 16)


class SlotsResponse(BaseModel):
    city: str | None
    serviceable: bool
    slots: list[SlotView]
    message: str


class BookingResponse(BaseModel):
    booked: bool
    booking_id: int | None = None
    slot: SlotView | None = None
    message: str


def seed_slots(
    db: Database,
    settings: Settings,
    now: datetime | None = None,
    days: int = 14,
    capacity: int = 5,
) -> int:
    """Idempotently creates slots for the next `days` days; returns rows added."""
    today = (now or utcnow()).astimezone(settings.tz).date()
    added = 0
    with db.connect() as conn:
        for offset in range(1, days + 1):
            day = today + timedelta(days=offset)
            for city, centres in CENTRES.items():
                for centre in centres:
                    for hour in SLOT_HOURS:
                        starts = datetime.combine(day, time(hour), tzinfo=settings.tz)
                        cursor = conn.execute(
                            "INSERT OR IGNORE INTO slots (city, centre, starts_at, capacity) "
                            "VALUES (?, ?, ?, ?)",
                            (city, centre, to_iso(starts), capacity),
                        )
                        added += cursor.rowcount
    return added


def _view(row: sqlite3.Row, settings: Settings) -> SlotView:
    local = from_iso(row["starts_at"]).astimezone(settings.tz)
    hour12 = local.hour % 12 or 12
    spoken = f"{local:%A}, {local.day} {local:%B} at {hour12}:{local:%M} {local:%p}, {row['centre']}"
    return SlotView(
        slot_id=row["id"],
        city=row["city"],
        centre=row["centre"],
        starts_at=local,
        spoken=spoken,
    )


def list_open_slots(
    db: Database,
    settings: Settings,
    city: str,
    now: datetime | None = None,
    limit: int = 3,
) -> SlotsResponse:
    canonical = canonical_city(city)
    if canonical is None:
        return SlotsResponse(
            city=None,
            serviceable=False,
            slots=[],
            message=f"There is no onboarding centre in {city} yet.",
        )
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM slots WHERE city = ? AND starts_at > ? AND booked < capacity "
            "ORDER BY starts_at, centre LIMIT ?",
            (canonical, to_iso(now or utcnow()), limit),
        ).fetchall()
    slots = [_view(row, settings) for row in rows]
    message = (
        f"{len(slots)} onboarding slot{'s' if len(slots) != 1 else ''} available in {canonical}."
        if slots
        else f"No onboarding slots are open in {canonical} right now."
    )
    return SlotsResponse(city=canonical, serviceable=True, slots=slots, message=message)


def _existing_booking(conn: sqlite3.Connection, interaction_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT b.id AS booking_id, s.* FROM bookings b JOIN slots s ON s.id = b.slot_id "
        "WHERE b.interaction_id = ?",
        (interaction_id,),
    ).fetchone()


def has_booking(db: Database, interaction_id: str) -> bool:
    with db.connect() as conn:
        return _existing_booking(conn, interaction_id) is not None


def book_slot(
    db: Database,
    settings: Settings,
    request: BookingRequest,
    now: datetime | None = None,
) -> BookingResponse:
    """Books a slot for a qualified lead. Idempotent per `interaction_id`.

    Business rejections are returned as `booked=False` with a speakable message
    rather than raised, so the agent can recover on the call.
    """
    decision = qualification.evaluate(request)
    if not decision.qualified:
        return BookingResponse(
            booked=False, message=f"Cannot book: {decision.message} Do not offer a slot."
        )

    stamp = to_iso(now or utcnow())
    with db.connect() as conn:
        existing = _existing_booking(conn, request.interaction_id)
        if existing:
            return _booked(existing, existing["booking_id"], settings)

        slot = conn.execute("SELECT * FROM slots WHERE id = ?", (request.slot_id,)).fetchone()
        if slot is None or slot["city"] != canonical_city(request.city):
            return BookingResponse(
                booked=False,
                message="That slot is not available in the lead's city. Fetch slots again.",
            )
        taken = conn.execute(
            "UPDATE slots SET booked = booked + 1 WHERE id = ? AND booked < capacity AND starts_at > ?",
            (request.slot_id, stamp),
        )
        if taken.rowcount == 0:
            return BookingResponse(
                booked=False, message="That slot was just taken. Fetch slots again and offer another."
            )
        cursor = conn.execute(
            "INSERT INTO bookings (interaction_id, slot_id, name, phone, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (request.interaction_id, request.slot_id, request.name, request.phone, stamp),
        )
        return _booked(slot, cursor.lastrowid, settings)


def _booked(slot: sqlite3.Row, booking_id: int | None, settings: Settings) -> BookingResponse:
    view = _view(slot, settings)
    return BookingResponse(
        booked=True,
        booking_id=booking_id,
        slot=view,
        message=f"Booked for {view.spoken}.",
    )
