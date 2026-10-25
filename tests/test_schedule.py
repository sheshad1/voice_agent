from datetime import datetime
from zoneinfo import ZoneInfo

from rider_agent.models import CallbackWindow
from rider_agent.schedule import callback_time, clamp_to_window, in_working_hours

IST = ZoneInfo("Asia/Kolkata")


def ist(hour: int, minute: int = 0, day: int = 26) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def test_working_hours_boundaries(settings):
    assert in_working_hours(ist(9), settings)
    assert in_working_hours(ist(20, 59), settings)
    assert not in_working_hours(ist(8, 59), settings)
    assert not in_working_hours(ist(21), settings)


def test_evening_lead_waits_for_next_morning(settings):
    assert clamp_to_window(ist(22), settings) == ist(9, day=27)


def test_early_lead_waits_for_opening(settings):
    assert clamp_to_window(ist(6), settings) == ist(9)


def test_in_window_time_is_unchanged(settings):
    assert clamp_to_window(ist(15), settings) == ist(15)


def test_callback_uses_requested_window_today(settings):
    assert callback_time(CallbackWindow.EVENING, settings, ist(12)) == ist(18)


def test_callback_rolls_to_tomorrow_when_window_too_close(settings):
    assert callback_time(CallbackWindow.AFTERNOON, settings, ist(13, 30)) == ist(14, day=27)


def test_callback_defaults_to_morning(settings):
    assert callback_time(None, settings, ist(12)) == ist(10, day=27)
