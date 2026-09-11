# tests/evaluation/test_report.py
"""Report writer tests (spec §4.6): naming, shape, and hygiene."""

import json

from evaluation.model import (
    EventSummary,
    RunRecord,
    Scenario,
    ScenarioResult,
)
from evaluation.report import write_report


def _result() -> ScenarioResult:
    scenario = Scenario(
        name="goblin-skirmish", description="d", seed=42, steps=("attack goblin scout",)
    )
    run = RunRecord(
        run_index=0,
        seed=42,
        event_summaries=(
            EventSummary(sequence=1, event_type="combat_started"),
            EventSummary(sequence=2, event_type="turn_started", actor="Arin"),
        ),
        invocation_summaries=(),
        turn_reports=("accepted",),
        party_messages=("Brix: Focus the nearest standing foe.",),
        duration_ms=120,
    )
    return ScenarioResult(
        scenario=scenario,
        provider="fake",
        model="z-ai/glm-5.3-flash",
        runs=(run,),
        checks=(),
        metrics={"legal_action_rate": 1.0, "rejection_count": 0},
        rejection_reasons={},
    )


def test_write_report_writes_parseable_json_with_the_contract_name(tmp_path) -> None:
    path = write_report(_result(), tmp_path)

    assert path.parent == tmp_path
    assert path.name.startswith("goblin-skirmish-fake-z-ai-glm-5.3-flash-42-")
    assert path.name.endswith(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["scenario"]["name"] == "goblin-skirmish"
    assert payload["provider"] == "fake"
    assert payload["metrics"]["legal_action_rate"] == 1.0
    assert payload["runs"][0]["event_types"] == ["combat_started", "turn_started"]
    assert payload["runs"][0]["party_messages"] == ["Brix: Focus the nearest standing foe."]


def test_write_report_creates_a_missing_out_dir(tmp_path) -> None:
    out_dir = tmp_path / "nested" / "eval-results"

    path = write_report(_result(), out_dir)

    assert out_dir.is_dir()
    assert path.exists()


def test_report_never_contains_secrets_or_prompts(tmp_path) -> None:
    path = write_report(_result(), tmp_path)

    text = path.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" not in text
    assert "api_key" not in text.lower()
    assert "prompt" not in text.lower()