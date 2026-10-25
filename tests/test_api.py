import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from rider_agent import leads
from rider_agent.api.app import create_app
from rider_agent.db import Database
from rider_agent.errors import DialerError
from rider_agent.models import Language
from rider_agent.sarvam_client import SarvamClient

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_tools_reject_bad_credentials(client, headers):
    assert client.get("/slots", params={"city": "Pune"}, headers=headers).status_code == 401


def test_fails_closed_without_configured_key(settings):
    settings.backend_api_key = SecretStr("")
    app_client = TestClient(create_app(settings))
    assert app_client.get("/slots", params={"city": "Pune"}, headers=HEADERS).status_code == 503


def test_token_query_param_authenticates_webhooks(client):
    response = client.post(
        "/webhooks/call-status",
        params={"token": "test-key"},
        json={"attempt_id": "x", "status": "failed"},
    )
    assert response.status_code == 404


def test_full_call_flow_over_http(client, settings):
    slots = client.get("/slots", params={"city": "Bangalore"}, headers=HEADERS).json()
    assert slots["serviceable"]
    slot_id = slots["slots"][0]["slot_id"]

    answers = {
        "interaction_id": "call-1",
        "intent": "interested",
        "has_vehicle": "yes",
        "docs_ready": "yes",
        "city": "Bangalore",
    }
    booked = client.post("/bookings", json={**answers, "slot_id": str(slot_id)}, headers=HEADERS).json()
    assert booked["booked"]

    record = client.post(
        "/crm/outcomes", json={**answers, "outcome": "qualified_booked", "slot_id": slot_id}, headers=HEADERS
    ).json()
    assert record["outcome"] == "qualified_booked"
    assert record["matches_agent"] is True


def test_booking_rejects_unqualified_lead_with_speakable_message(client):
    slot_id = client.get("/slots", params={"city": "Pune"}, headers=HEADERS).json()["slots"][0]["slot_id"]
    response = client.post(
        "/bookings",
        json={
            "interaction_id": "c2",
            "slot_id": slot_id,
            "intent": "interested",
            "has_vehicle": "no",
            "docs_ready": "yes",
            "city": "Pune",
        },
        headers=HEADERS,
    ).json()
    assert response["booked"] is False
    assert "two-wheeler" in response["message"]


def test_outbound_payload_and_attempt_id(settings):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["X-API-Key"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"attempt_id": "att-1"})

    sarvam = SarvamClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    db = Database(settings.db_path)
    db.init_schema()
    lead, _ = leads.add_lead(db, "Asha", "9876543210", "Pune", Language.ENGLISH)

    assert sarvam.place_call(lead) == "att-1"
    assert captured["url"].endswith("/orgs/org1/workspaces/ws1/outbounds")
    assert captured["key"] == "sarvam-test"
    body = captured["body"]
    assert body["user_config"]["user_phone_number"] == "+919876543210"
    assert body["app_config"]["app_overrides"]["initial_language_name"] == "English"
    assert "Asha" in body["app_config"]["app_overrides"]["initial_bot_message"]
    assert "Shubh" in body["app_config"]["app_overrides"]["initial_bot_message"]
    assert body["webhook_config"]["metadata"] == {"lead_id": lead.id}
    assert body["webhook_config"]["url"].endswith("?token=test-key")


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, json={"unexpected": True}), httpx.Response(200, text="<html>")],
)
def test_outbound_failures_surface_as_dialer_error_without_leaking_key(settings, response):
    sarvam = SarvamClient(settings, httpx.Client(transport=httpx.MockTransport(lambda _: response)))
    db = Database(settings.db_path)
    db.init_schema()
    lead, _ = leads.add_lead(db, "Asha", "9876543210", "Pune")
    with pytest.raises(DialerError) as error:
        sarvam.place_call(lead)
    assert "sarvam-test" not in str(error.value)
