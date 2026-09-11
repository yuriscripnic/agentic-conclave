# tests/evaluation/test_offline_scenarios.py
"""Offline end-to-end checks for the two later scenarios (spec §4.4)."""

from evaluation.runner import run_scenario
from evaluation.scenarios import get_scenario


def test_instruction_following_passes_offline() -> None:
    scenario = get_scenario("instruction-following")

    result = run_scenario(scenario, seed=42, repeat=1, provider="fake")

    assert result.status == "ok"
    assert all(check.passed for check in result.checks)
    fidelity = [
        event
        for event in result.runs[0].event_summaries
        if event.event_type == "attack_requested"
        and event.actor == "Arin"
        and event.target == "Orc Brute"
    ]
    assert fidelity  # the human instruction, executed by the rules engine


def test_cooperation_smoke_passes_offline() -> None:
    scenario = get_scenario("cooperation-smoke")

    result = run_scenario(scenario, seed=42, repeat=1, provider="fake")

    assert result.status == "ok"
    assert all(check.passed for check in result.checks)
    assert result.metrics["party_message_count"] >= 1