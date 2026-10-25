from pathlib import Path

import pytest

from rider_agent import booking, calls, crm, leads
from rider_agent.models import CallStatusPayload, Language, OutcomeRequest

APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


@pytest.fixture
def populated(db, settings, now):
    lead, _ = leads.add_lead(db, "Asha", "9876543210", "Bengaluru", Language.HINDI, now=now)
    booking.seed_slots(db, settings, now=now)
    calls.record_attempt(db, lead.id, "a1", now)
    calls.handle_call_status(
        db,
        settings,
        CallStatusPayload(
            attempt_id="a1",
            status="connected",
            interaction_id="call-1",
            final_agent_variables={"intent": "not_interested"},
            interaction_transcript=[{"role": "agent", "en_text": "Hello Asha"}],
        ),
        now,
    )
    crm.record_outcome(db, settings, OutcomeRequest(interaction_id="call-2", intent="interested"), now)
    return db


def test_dashboard_renders_with_data(populated, settings, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DB_PATH", str(settings.db_path))
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert [m.label for m in app.metric][:3] == ["Leads", "Calls placed", "Connect rate"]


def test_dashboard_warns_when_database_missing(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DB_PATH", str(tmp_path / "missing.db"))
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert app.warning
