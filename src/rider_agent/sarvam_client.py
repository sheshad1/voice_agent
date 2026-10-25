"""Outbound dialing through the Sarvam Voice Agents instant-outbound API."""

import httpx

from rider_agent.config import Settings
from rider_agent.errors import DialerError
from rider_agent.models import Language, Lead

GREETINGS: dict[Language, str] = {
    Language.HINDI: (
        "नमस्ते {name} जी, मैं शुभ, Swiggy का AI असिस्टेंट बोल रहा हूँ। "
        "आपके डिलीवरी पार्टनर साइनअप के बारे में कॉल किया है। क्या अभी बात करने का सही समय है?"
    ),
    Language.ENGLISH: (
        "Hello {name}, this is Shubh, an AI assistant calling from Swiggy about your "
        "delivery-partner signup. Is now a good time?"
    ),
}


class SarvamClient:
    """Places outbound calls; satisfies the scheduler's `Dialer` protocol."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.Client(
            timeout=20.0, trust_env=settings.sarvam_use_env_proxy
        )

    @property
    def _url(self) -> str:
        s = self._settings
        return (
            f"{s.sarvam_base_url}/api/outbounds/v1/orgs/{s.sarvam_org_id}"
            f"/workspaces/{s.sarvam_workspace_id}/outbounds"
        )

    def build_payload(self, lead: Lead) -> dict:
        s = self._settings
        token = s.backend_api_key.get_secret_value()
        return {
            "app_config": {
                "app_id": s.sarvam_app_id,
                "app_version": s.sarvam_app_version,
                "connection_config": {
                    "connection_id": s.sarvam_connection_id,
                    "agent_phone_number": s.sarvam_agent_phone_number,
                },
                "agent_variables": {
                    "lead_id": str(lead.id),
                    "lead_name": lead.name,
                    "lead_city": lead.city or "",
                    "preferred_language": lead.language.value,
                },
                "app_overrides": {
                    "initial_language_name": lead.language.value,
                    "initial_bot_message": GREETINGS[lead.language].format(name=lead.name),
                },
            },
            "user_config": {"user_phone_number": lead.phone},
            "webhook_config": {
                "url": f"{s.public_base_url}/webhooks/call-status?token={token}",
                "metadata": {"lead_id": lead.id},
            },
        }

    def place_call(self, lead: Lead) -> str:
        """Dials the lead and returns Sarvam's attempt id.

        Raises:
            DialerError: On transport failure, a non-2xx response or a malformed reply.
        """
        try:
            response = self._http.post(
                self._url,
                json=self.build_payload(lead),
                headers={"X-API-Key": self._settings.sarvam_api_key.get_secret_value()},
            )
            response.raise_for_status()
            return str(response.json()["attempt_id"])
        except httpx.HTTPStatusError as exc:
            raise DialerError(f"Sarvam returned HTTP {exc.response.status_code}") from None
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise DialerError(f"Outbound call failed: {type(exc).__name__}") from None
