"""UTC-only helpers; every timestamp is stored as a UTC ISO-8601 string."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """Serialises an aware datetime as a UTC ISO string.

    Raises:
        ValueError: If `moment` is naive.
    """
    if moment.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware.")
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def from_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)
