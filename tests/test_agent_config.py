import csv
from pathlib import Path

import yaml

from rider_agent.models import (
    CallbackWindow,
    NotQualifiedReason,
    Outcome,
    OutcomeRequest,
    QualificationAnswers,
)

AGENT = Path(__file__).resolve().parents[1] / "agent"


def load(name: str) -> dict:
    return yaml.safe_load((AGENT / name).read_text(encoding="utf-8"))


def test_output_variable_values_match_backend_enums():
    outputs = {v["name"]: v for v in load("variables.yaml")["outputs"]}
    assert set(outputs["outcome"]["allowed_values"]) == {e.value for e in Outcome}
    assert set(outputs["not_qualified_reason"]["allowed_values"]) == {e.value for e in NotQualifiedReason}
    assert set(outputs["callback_window"]["allowed_values"]) == {e.value for e in CallbackWindow}


def test_every_deployed_enum_value_is_understood_by_the_backend():
    outputs = {v["name"]: v for v in load("variables.yaml")["outputs"]}
    for value in outputs["intent"]["allowed_values"]:
        assert QualificationAnswers(intent=value).intent is not None, value
    for name in ("has_vehicle", "docs_ready"):
        for value in outputs[name]["allowed_values"]:
            assert getattr(QualificationAnswers(**{name: value}), name) is not None, (name, value)
    for value in outputs["do_not_call"]["allowed_values"]:
        assert OutcomeRequest(interaction_id="x", do_not_call=value).do_not_call is not None, value


def test_every_output_variable_is_accepted_by_crm_endpoint():
    outputs = {v["name"] for v in load("variables.yaml")["outputs"]}
    assert outputs <= set(OutcomeRequest.model_fields)


def test_crm_tool_body_only_sends_known_fields():
    tool = next(t for t in load("tools.yaml")["tools"] if t["name"] == "push_crm_outcome")
    assert tool["run"] == "on_end"
    assert set(tool["body"]) <= set(OutcomeRequest.model_fields)


def test_instruction_uses_input_variables_and_calls_tools_by_name():
    text = (AGENT / "instruction.md").read_text(encoding="utf-8")
    for name in [v["name"] for v in load("variables.yaml")["inputs"]]:
        assert f"{{{{{name}}}}}" in text, name
    for tool in ("get_slots", "book_slot"):
        assert f"tool:{tool}" in text


def test_tools_use_secret_reference_not_inline_credentials():
    for tool in load("tools.yaml")["tools"]:
        assert tool["headers"]["X-API-Key"].startswith("<secret:")


def test_approved_faq_is_present_and_well_formed():
    with (AGENT / "knowledge" / "rider_faq.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 21
    assert all(row["Question"].strip() and row["Answer"].strip() for row in rows)


def test_scenarios_are_complete():
    scenarios = load("tests/scenarios.yaml")["scenarios"]
    assert len(scenarios) >= 10
    assert len({s["name"] for s in scenarios}) == len(scenarios)
    assert all(s["user_scenario"] and s["expected_behaviours"] for s in scenarios)
