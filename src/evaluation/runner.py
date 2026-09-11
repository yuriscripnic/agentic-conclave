"""Scenario runner: fresh seeded sessions through the application layer (spec §4.3).

Evaluation contains no game rules and mutates game state only through
application services (§71). One correlation id per step (Plan 8).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from ai.models.profiles import load_model_profiles
from ai.models.types import LLMInvocation
from application.views import TurnReport
from domain.events.collector import EventEnvelope
from evaluation.errors import EvaluationError
from evaluation.metrics import compute_metrics
from evaluation.model import (
    CheckResult,
    EventSummary,
    InvocationSummary,
    RunRecord,
    Scenario,
    ScenarioResult,
)
from session import (
    CONFIG_DIR,
    GameSession,
    SessionConfig,
    advance,
    apply_input,
    open_session,
)

_PROVIDER_MODES = {"fake": ("fake", "fake"), "openrouter": ("llm", "llm")}
_PARTY_SNAPSHOT_LIMIT = 128


def run_scenario(
    scenario: Scenario,
    *,
    seed: int,
    repeat: int,
    provider: str,
    db: str = "memory",
) -> ScenarioResult:
    """Run a scenario repeat times; isolate a failing run (spec §5)."""
    if provider not in _PROVIDER_MODES:
        raise EvaluationError(f"unknown provider: {provider!r}")
    if repeat < 1:
        raise EvaluationError(f"repeat must be >= 1, got {repeat}")
    agent_mode, gm_mode = _PROVIDER_MODES[provider]
    config = SessionConfig(
        db=db,
        agent_mode=agent_mode,
        gm_mode=gm_mode,
        provider=provider if provider == "openrouter" else None,
    )
    model = load_model_profiles(CONFIG_DIR / "llm.toml").get("player").model

    runs: list[RunRecord] = []
    for run_index in range(repeat):
        try:
            runs.append(_run_once(scenario, config, run_index, seed))
        except Exception as error:  # scenario isolation, spec §5
            partial = ScenarioResult(
                scenario=scenario,
                provider=provider,
                model=model,
                runs=tuple(runs),
                checks=(),
                metrics={},
                rejection_reasons=_rejection_reasons(tuple(runs)),
                status="error",
                error=str(error),
            )
            return replace(partial, metrics=compute_metrics(partial))

    base = ScenarioResult(
        scenario=scenario,
        provider=provider,
        model=model,
        runs=tuple(runs),
        checks=(),
        metrics={},
        rejection_reasons=_rejection_reasons(tuple(runs)),
    )
    result = replace(base, metrics=compute_metrics(base))
    checks = tuple(
        CheckResult(
            name=check.name,
            description=check.description,
            passed=check.evaluate(result),
        )
        for check in scenario.checks
    )
    return replace(result, checks=checks)


def _run_once(
    scenario: Scenario, config: SessionConfig, run_index: int, seed: int
) -> RunRecord:
    """One fresh session, driven step by step, then reduced to a RunRecord."""
    started = time.perf_counter()
    session = open_session(replace(config, seed=seed))
    turn_reports: list[TurnReport] = []

    for step in scenario.steps:
        _drain(session, turn_reports)
        view = session.game_service.get_view(session.game_id)
        if view.status == "ended":
            continue  # later steps are skipped once the fight is decided
        outcome = apply_input(session, step)
        if outcome.turn_report is not None:
            turn_reports.append(outcome.turn_report)
    _drain(session, turn_reports)
    duration_ms = int((time.perf_counter() - started) * 1000)

    events = session.game_service.get_events(session.game_id)
    view = session.game_service.get_view(session.game_id)
    name_by_id = {member.id: member.name for member in (*view.party, *view.enemies)}
    return RunRecord(
        run_index=run_index,
        seed=seed,
        event_summaries=tuple(
            _summarize_event(envelope, name_by_id) for envelope in events
        ),
        invocation_summaries=tuple(
            _summarize_invocation(invocation)
            for invocation in session.telemetry.invocations()
        ),
        turn_reports=tuple(
            f"{'accepted' if report.accepted else 'rejected'}"
            + (f": {report.reason}" if report.reason else "")
            for report in turn_reports
        ),
        party_messages=tuple(
            f"{message.actor_name}: {message.text}"
            for message in session.party_board.recent(limit=_PARTY_SNAPSHOT_LIMIT)
        ),
        duration_ms=duration_ms,
    )


def _drain(session: GameSession, turn_reports: list[TurnReport]) -> None:
    """Drive non-player turns until it is the human's turn or the fight is over."""
    while (pending := advance(session)) is not None:
        turn_reports.append(pending.turn_report)


def _rejection_reasons(runs: tuple[RunRecord, ...]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for run in runs:
        for event in run.event_summaries:
            if event.event_type == "action_rejected" and event.detail:
                reasons[event.detail] = reasons.get(event.detail, 0) + 1
    return reasons


def _summarize_invocation(invocation: LLMInvocation) -> InvocationSummary:
    """Metrics only — never prompts, payloads, or reasoning (§34/§50)."""
    return InvocationSummary(
        agent_id=invocation.agent_id,
        operation=invocation.operation,
        status=invocation.status,
        attempt=invocation.attempt,
        latency_ms=invocation.latency_ms,
        input_tokens=invocation.input_tokens,
        output_tokens=invocation.output_tokens,
        estimated_cost_usd=invocation.estimated_cost_usd,
    )


def _summarize_event(
    envelope: EventEnvelope, name_by_id: Mapping[str, str]
) -> EventSummary:
    """Reduce one envelope to comparable facts, ids resolved to names."""
    payload = envelope.payload
    event_type = envelope.event_type

    def _name(field: str) -> str:
        value = str(payload[field])
        return name_by_id.get(value, value)

    actor = target = detail = None
    if event_type == "attack_requested":
        actor, target = _name("attacker_id"), _name("target_id")
    elif event_type == "attack_resolved":
        actor, target = _name("attacker_id"), _name("target_id")
        detail = (
            f"roll {payload['roll']}+{payload['attack_bonus']}={payload['total']} "
            f"vs AC {payload['target_ac']} hit={payload['hit']} crit={payload['critical']}"
        )
    elif event_type == "action_rejected":
        actor = _name("actor_id")
        detail = str(payload["reason"])
    elif event_type == "damage_applied":
        actor = _name("character_id")
        detail = f"-{payload['amount']} ({payload['hp_after']} hp)"
    elif event_type == "character_defeated":
        actor = _name("character_id")
    elif event_type == "initiative_rolled":
        actor = _name("character_id")
        detail = f"total {payload['total']}"
    elif event_type == "combat_started":
        # Domain contract: combat_started carries participant_ids as a list.
        participants = cast("list[str]", payload["participant_ids"])
        detail = f"round {payload['round_number']}: {len(participants)} participants"
    elif event_type == "combat_ended":
        detail = f"round {payload['round_number']}: {payload['winner_side']} wins"
    elif event_type in ("turn_started", "turn_ended"):
        actor = _name("actor_id")
    return EventSummary(
        sequence=envelope.sequence,
        event_type=event_type,
        actor=actor,
        target=target,
        detail=detail,
    )