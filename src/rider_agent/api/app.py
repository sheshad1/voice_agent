"""FastAPI app: booking and CRM tools for the agent, plus Sarvam's call webhook."""

import hmac
import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from rider_agent import __version__, booking, calls, crm
from rider_agent.config import Settings, get_settings
from rider_agent.db import Database
from rider_agent.errors import UnknownAttemptError
from rider_agent.models import BookingRequest, CallStatusPayload, OutcomeRecord, OutcomeRequest

logger = logging.getLogger("rider_agent.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.db_path)
    db.init_schema()
    booking.seed_slots(db, settings)

    app = FastAPI(title="Swiggy Rider Onboarding Backend", version=__version__)

    def require_api_key(
        x_api_key: Annotated[str | None, Header()] = None,
        token: Annotated[str | None, Query()] = None,
    ) -> None:
        expected = settings.backend_api_key.get_secret_value()
        if not expected:
            raise HTTPException(status_code=503, detail="BACKEND_API_KEY is not configured.")
        supplied = x_api_key or token or ""
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Invalid API key.")

    secured = [Depends(require_api_key)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/slots", response_model=booking.SlotsResponse, dependencies=secured)
    def get_slots(city: str, limit: Annotated[int, Query(ge=1, le=10)] = 3):
        return booking.list_open_slots(db, settings, city, limit=limit)

    @app.post("/bookings", response_model=booking.BookingResponse, dependencies=secured)
    def create_booking(request: BookingRequest):
        return booking.book_slot(db, settings, request)

    @app.post("/crm/outcomes", response_model=OutcomeRecord, dependencies=secured)
    def push_outcome(request: OutcomeRequest):
        return crm.record_outcome(db, settings, request)

    @app.post("/webhooks/call-status", dependencies=secured)
    def call_status(payload: CallStatusPayload) -> dict[str, str]:
        try:
            result = calls.handle_call_status(db, settings, payload)
        except UnknownAttemptError:
            logger.warning("Webhook for unknown attempt %s", payload.attempt_id)
            raise HTTPException(status_code=404, detail="Unknown attempt.") from None
        return {"result": result}

    return app
