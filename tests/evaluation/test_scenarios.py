# tests/evaluation/test_scenarios.py
"""Scenario registry tests (spec §4.2)."""

import pytest

from evaluation.errors import EvaluationError
from evaluation.scenarios import get_scenario


def test_get_scenario_returns_goblin_skirmish() -> None:
    scenario = get_scenario("goblin-skirmish")

    assert scenario.seed == 42
    assert scenario.repeat_runs == 2
    assert scenario.steps == ("attack goblin scout", "attack goblin skulker")
    assert {check.name for check in scenario.checks} == {
        "no-rejections",
        "skirmish-enemies-defeated",
        "consistent-runs",
    }


def test_get_scenario_unknown_name_raises_evaluation_error() -> None:
    with pytest.raises(EvaluationError, match="unknown scenario"):
        get_scenario("dragon-hoard")


def test_registry_holds_the_three_scenarios() -> None:
    from evaluation.scenarios import SCENARIOS

    assert set(SCENARIOS) == {
        "goblin-skirmish",
        "instruction-following",
        "cooperation-smoke",
    }