# tests/evaluation/test_runner.py
"""Runner end-to-end over offline scripted gateways (spec §4.3)."""

import pytest

from evaluation import runner as runner_module
from evaluation.errors import EvaluationError
from evaluation.runner import run_scenario
from evaluation.scenarios import get_scenario


def test_run_scenario_goblin_skirmish_offline() -> None:
    scenario = get_scenario("goblin-skirmish")

    result = run_scenario(scenario, seed=42, repeat=2, provider="fake")

    assert result.status == "ok"
    assert result.error is None
    assert len(result.runs) == 2
    assert result.runs[0].seed == 42
    assert result.runs[0].event_summaries  # a real fight happened
    assert result.runs[0].invocation_summaries  # gateway calls were recorded
    assert result.runs[0].party_messages  # scripted agents post chatter
    assert result.runs[0].turn_reports
    assert all(check.passed for check in result.checks)
    assert result.metrics["consistency_agreement"] == 1.0
    assert result.rejection_reasons == {}


def test_run_scenario_is_reproducible_across_calls() -> None:
    scenario = get_scenario("goblin-skirmish")

    first = run_scenario(scenario, seed=42, repeat=1, provider="fake")
    second = run_scenario(scenario, seed=42, repeat=1, provider="fake")

    assert [event.event_type for event in first.runs[0].event_summaries] == [
        event.event_type for event in second.runs[0].event_summaries
    ]


def test_failing_run_reports_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = get_scenario("goblin-skirmish")

    def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("gateway exploded")

    monkeypatch.setattr(runner_module, "_run_once", _boom)

    result = run_scenario(scenario, seed=42, repeat=2, provider="fake")

    assert result.status == "error"
    assert "gateway exploded" in str(result.error)
    assert result.checks == ()


def test_unknown_provider_raises_evaluation_error() -> None:
    scenario = get_scenario("goblin-skirmish")

    with pytest.raises(EvaluationError, match="unknown provider"):
        run_scenario(scenario, seed=42, repeat=1, provider="ollama")


def test_repeat_below_one_raises_evaluation_error() -> None:
    scenario = get_scenario("goblin-skirmish")

    with pytest.raises(EvaluationError, match="repeat"):
        run_scenario(scenario, seed=42, repeat=0, provider="fake")