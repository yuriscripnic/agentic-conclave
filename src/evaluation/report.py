"""JSON report writer (spec §4.6): no secrets, no prompts, no payloads (§34/§50)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.errors import EvaluationError
from evaluation.model import ScenarioResult


def write_report(result: ScenarioResult, out_dir: Path) -> Path:
    """Write one scenario's JSON report and return its path."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise EvaluationError(
            f"cannot write report directory {out_dir}: {error}"
        ) from error
    seed = result.runs[0].seed if result.runs else result.scenario.seed
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    model = result.model.replace("/", "-")
    path = out_dir / f"{result.scenario.name}-{result.provider}-{model}-{seed}-{stamp}.json"
    path.write_text(json.dumps(_payload(result), indent=2) + "\n", encoding="utf-8")
    return path


def _payload(result: ScenarioResult) -> dict[str, object]:
    return {
        "scenario": {
            "name": result.scenario.name,
            "description": result.scenario.description,
            "seed": result.scenario.seed,
            "steps": list(result.scenario.steps),
        },
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "error": result.error,
        "checks": [
            {"name": check.name, "description": check.description, "passed": check.passed}
            for check in result.checks
        ],
        "metrics": dict(result.metrics),
        "rejection_reasons": dict(result.rejection_reasons),
        "runs": [
            {
                "run_index": run.run_index,
                "seed": run.seed,
                "duration_ms": run.duration_ms,
                "event_types": [event.event_type for event in run.event_summaries],
                "events": [
                    {
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "actor": event.actor,
                        "target": event.target,
                        "detail": event.detail,
                    }
                    for event in run.event_summaries
                ],
                "invocations": [
                    {
                        "agent_id": invocation.agent_id,
                        "operation": invocation.operation,
                        "status": invocation.status,
                        "attempt": invocation.attempt,
                        "latency_ms": invocation.latency_ms,
                        "input_tokens": invocation.input_tokens,
                        "output_tokens": invocation.output_tokens,
                        "estimated_cost_usd": invocation.estimated_cost_usd,
                    }
                    for invocation in run.invocation_summaries
                ],
                "turn_reports": list(run.turn_reports),
                "party_messages": list(run.party_messages),
            }
            for run in result.runs
        ],
    }