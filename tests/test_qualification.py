import pytest

from rider_agent.models import (
    Intent,
    NotQualifiedReason,
    Outcome,
    OutcomeRequest,
    QualificationAnswers,
    normalize_phone,
)
from rider_agent.qualification import evaluate


def answers(**kwargs) -> QualificationAnswers:
    base = {"intent": "interested", "has_vehicle": "yes", "docs_ready": "yes", "city": "Pune"}
    return QualificationAnswers.model_validate({**base, **kwargs})


@pytest.mark.parametrize(
    ("overrides", "outcome", "reason"),
    [
        ({"intent": "not_interested"}, Outcome.NOT_INTERESTED, None),
        ({"intent": "call_back_later"}, Outcome.FOLLOW_UP_NEEDED, None),
        ({"intent": None}, Outcome.FOLLOW_UP_NEEDED, None),
        ({"has_vehicle": "no"}, Outcome.NOT_QUALIFIED, NotQualifiedReason.NO_VEHICLE),
        ({"has_vehicle": "NA"}, Outcome.FOLLOW_UP_NEEDED, None),
        ({"city": "Jaipur"}, Outcome.NOT_QUALIFIED, NotQualifiedReason.OUT_OF_SERVICE_AREA),
        ({"city": ""}, Outcome.FOLLOW_UP_NEEDED, None),
    ],
)
def test_checklist_outcomes(overrides, outcome, reason):
    decision = evaluate(answers(**overrides))
    assert decision.outcome is outcome
    assert decision.reason is reason
    assert not decision.qualified


def test_checklist_order_reports_first_failure():
    decision = evaluate(answers(has_vehicle="no", docs_ready="no", city="Jaipur"))
    assert decision.reason is NotQualifiedReason.NO_VEHICLE


def test_missing_documents_do_not_block_qualification():
    for value in ("no", "NA", None):
        assert evaluate(answers(docs_ready=value), booked=True).outcome is Outcome.QUALIFIED_BOOKED


def test_qualified_is_booked_only_with_a_slot():
    assert evaluate(answers()).outcome is Outcome.FOLLOW_UP_NEEDED
    assert evaluate(answers()).qualified
    assert evaluate(answers(), booked=True).outcome is Outcome.QUALIFIED_BOOKED


def test_city_aliases_are_served():
    assert evaluate(answers(city="Bangalore"), booked=True).qualified
    assert evaluate(answers(city="बेंगलुरु"), booked=True).qualified


def test_callback_alias_maps_to_call_back_later():
    assert answers(intent="callback").intent is Intent.CALL_BACK_LATER
    assert evaluate(answers(intent="callback")).outcome is Outcome.FOLLOW_UP_NEEDED


def test_true_false_strings_are_understood():
    assert answers(has_vehicle="true").has_vehicle is True
    assert answers(has_vehicle="False").has_vehicle is False


def test_agent_strings_parse_leniently():
    request = OutcomeRequest.model_validate(
        {
            "interaction_id": "i1",
            "intent": "Call Back Later",
            "has_vehicle": "Haan",
            "slot_id": "12",
            "lead_id": "N/A",
            "callback_window": "Evening",
        }
    )
    assert request.intent is Intent.CALL_BACK_LATER
    assert request.has_vehicle is True
    assert request.slot_id == 12
    assert request.lead_id is None
    assert request.callback_window.value == "evening"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("98765 43210", "+919876543210"), ("09876543210", "+919876543210"), ("+14155550100", "+14155550100")],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "5876543210", "+91 12345 67890"])
def test_normalize_phone_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)
