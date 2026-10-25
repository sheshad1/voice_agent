"""Deterministic qualification rules.

The backend, not the LLM, is the source of truth for the verdict, so the same
answers always produce the same outcome.
"""

from rider_agent.cities import canonical_city
from rider_agent.models import (
    Decision,
    Intent,
    NotQualifiedReason,
    Outcome,
    QualificationAnswers,
)


def _incomplete(message: str) -> Decision:
    return Decision(outcome=Outcome.FOLLOW_UP_NEEDED, qualified=False, message=message)


def evaluate(answers: QualificationAnswers, booked: bool = False) -> Decision:
    """Applies the checklist in order: intent, vehicle, city.

    Documents are captured for the CRM but never block qualification, because
    the approved FAQ states none are needed to start onboarding.

    Args:
        answers: Checklist answers captured on the call.
        booked: Whether an onboarding slot is already booked for this call.

    Returns:
        The verdict. A lead who passes every check is `qualified`; the outcome
        is `QUALIFIED_BOOKED` only once a slot exists, otherwise follow-up.
    """
    if answers.intent is None:
        return _incomplete("Intent was not captured.")
    if answers.intent is Intent.NOT_INTERESTED:
        return Decision(
            outcome=Outcome.NOT_INTERESTED, qualified=False, message="Lead is not interested."
        )
    if answers.intent is Intent.CALL_BACK_LATER:
        return _incomplete("Lead asked for a call back.")

    if answers.has_vehicle is None:
        return _incomplete("Vehicle ownership was not captured.")
    if not answers.has_vehicle:
        return _not_qualified(NotQualifiedReason.NO_VEHICLE, "A two-wheeler is required.")

    if not answers.city:
        return _incomplete("City was not captured.")
    if canonical_city(answers.city) is None:
        return _not_qualified(
            NotQualifiedReason.OUT_OF_SERVICE_AREA, "No onboarding centre in this city yet."
        )

    if booked:
        return Decision(
            outcome=Outcome.QUALIFIED_BOOKED, qualified=True, message="Qualified and booked."
        )
    return Decision(
        outcome=Outcome.FOLLOW_UP_NEEDED,
        qualified=True,
        message="Qualified, but no onboarding slot is booked yet.",
    )


def _not_qualified(reason: NotQualifiedReason, message: str) -> Decision:
    return Decision(outcome=Outcome.NOT_QUALIFIED, qualified=False, reason=reason, message=message)
