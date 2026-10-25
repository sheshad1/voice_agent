"""Working-hours and call-back time arithmetic."""

from datetime import datetime, timedelta

from rider_agent.config import Settings
from rider_agent.models import CallbackWindow

_CALLBACK_HOURS: dict[CallbackWindow, int] = {
    CallbackWindow.MORNING: 10,
    CallbackWindow.AFTERNOON: 14,
    CallbackWindow.EVENING: 18,
}
_MIN_CALLBACK_LEAD = timedelta(hours=1)


def in_working_hours(moment: datetime, settings: Settings) -> bool:
    local = moment.astimezone(settings.tz)
    return settings.working_hours_start <= local.hour < settings.working_hours_end


def clamp_to_window(moment: datetime, settings: Settings) -> datetime:
    """Returns the earliest instant at or after `moment` inside working hours."""
    local = moment.astimezone(settings.tz)
    opening = local.replace(hour=settings.working_hours_start, minute=0, second=0, microsecond=0)
    if local.hour < settings.working_hours_start:
        return opening
    if local.hour >= settings.working_hours_end:
        return opening + timedelta(days=1)
    return local


def callback_time(window: CallbackWindow | None, settings: Settings, now: datetime) -> datetime:
    """Picks the next occurrence of the requested window, at least an hour out."""
    hour = _CALLBACK_HOURS[window or CallbackWindow.MORNING]
    local = now.astimezone(settings.tz)
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= local + _MIN_CALLBACK_LEAD:
        candidate += timedelta(days=1)
    return clamp_to_window(candidate, settings)
