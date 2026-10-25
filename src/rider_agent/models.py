"""Domain enums and pydantic models.

Values arriving from the voice agent are free-form strings, so the request
models parse leniently and treat anything unrecognised as "not captured".
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class Language(StrEnum):
    HINDI = "Hindi"
    ENGLISH = "English"


class Intent(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALL_BACK_LATER = "call_back_later"


class Outcome(StrEnum):
    QUALIFIED_BOOKED = "qualified_booked"
    NOT_QUALIFIED = "not_qualified"
    NOT_INTERESTED = "not_interested"
    FOLLOW_UP_NEEDED = "follow_up_needed"


class NotQualifiedReason(StrEnum):
    NO_VEHICLE = "no_vehicle"
    OUT_OF_SERVICE_AREA = "out_of_service_area"


class CallbackWindow(StrEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class LeadStatus(StrEnum):
    NEW = "new"
    DIALING = "dialing"
    RETRY = "retry"
    CALLBACK = "callback"
    COMPLETED = "completed"
    EXHAUSTED = "exhausted"
    DND = "dnd"


class CallStatus(StrEnum):
    INITIATED = "initiated"
    CONNECTED = "connected"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"


_TRUE = {"yes", "y", "true", "1", "haan", "ha", "han"}
_FALSE = {"no", "n", "false", "0", "nahi", "nahin"}
_EMPTY = {"", "na", "n/a", "null", "none", "unknown"}


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().casefold() in _EMPTY:
        return None
    return value


def _parse_tristate(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _lenient_enum(enum_cls: type[StrEnum], aliases: dict[str, StrEnum] | None = None):
    def parse(value: Any) -> Any:
        if value is None or isinstance(value, enum_cls):
            return value
        text = re.sub(r"[\s\-]+", "_", str(value).strip().casefold())
        if aliases and text in aliases:
            return aliases[text]
        try:
            return enum_cls(text)
        except ValueError:
            return None

    return parse


def _lenient_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


TriState = Annotated[bool | None, BeforeValidator(_parse_tristate)]
OptStr = Annotated[str | None, BeforeValidator(_blank_to_none)]
OptInt = Annotated[int | None, BeforeValidator(_lenient_int)]
OptIntent = Annotated[
    Intent | None,
    BeforeValidator(
        _lenient_enum(Intent, {"callback": Intent.CALL_BACK_LATER, "call_back": Intent.CALL_BACK_LATER})
    ),
]
OptWindow = Annotated[CallbackWindow | None, BeforeValidator(_lenient_enum(CallbackWindow))]


def normalize_phone(raw: str) -> str:
    """Returns an E.164 number, assuming India for bare 10-digit input.

    Raises:
        ValueError: If the number is not a plausible phone number.
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    if not 11 <= len(digits) <= 15:
        raise ValueError(f"Invalid phone number: {raw!r}")
    if digits.startswith("91") and (len(digits) != 12 or digits[2] not in "6789"):
        raise ValueError(f"Invalid Indian mobile number: {raw!r}")
    return "+" + digits


class Lead(BaseModel):
    id: int
    name: str
    phone: str
    city: str | None
    language: Language
    source: str
    status: LeadStatus
    unanswered_attempts: int
    next_attempt_at: datetime | None
    created_at: datetime


class QualificationAnswers(BaseModel):
    """The checklist answers captured on the call, in checklist order."""

    model_config = ConfigDict(extra="ignore")

    intent: OptIntent = None
    has_vehicle: TriState = None
    docs_ready: TriState = None
    city: OptStr = None


class BookingRequest(QualificationAnswers):
    interaction_id: str = Field(min_length=1)
    slot_id: int
    name: OptStr = None
    phone: OptStr = None


class OutcomeRequest(QualificationAnswers):
    interaction_id: str = Field(min_length=1)
    lead_id: OptInt = None
    attempt_id: OptStr = None
    phone: OptStr = None
    name: OptStr = None
    language: OptStr = None
    outcome: OptStr = None
    not_qualified_reason: OptStr = None
    slot_id: OptInt = None
    callback_window: OptWindow = None
    do_not_call: TriState = None
    transcript: OptStr = None


class SlotView(BaseModel):
    slot_id: int
    city: str
    centre: str
    starts_at: datetime
    spoken: str


class Decision(BaseModel):
    outcome: Outcome
    qualified: bool
    reason: NotQualifiedReason | None = None
    message: str


class OutcomeRecord(BaseModel):
    interaction_id: str
    outcome: Outcome
    reason: NotQualifiedReason | None
    matches_agent: bool | None
    lead_id: int | None


class CallStatusPayload(BaseModel):
    """Sarvam's call-attempt webhook body."""

    model_config = ConfigDict(extra="ignore")

    attempt_id: str
    status: CallStatus
    interaction_id: str | None = None
    duration: float | None = None
    failure_reason: str | None = None
    final_agent_variables: dict[str, Any] | None = None
    interaction_transcript: list[dict[str, Any]] | None = None
    webhook_config: dict[str, Any] | None = None

    def metadata_lead_id(self) -> int | None:
        metadata = (self.webhook_config or {}).get("metadata") or {}
        return _lenient_int(metadata.get("lead_id"))
