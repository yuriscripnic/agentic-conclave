"""Per-session RAM accumulator for LLM telemetry (Phase 17, spec §3.4)."""

from dataclasses import dataclass

from ai.models.types import LLMInvocation

_EMBED_OPERATION = "embed"


def _role_for(invocation: LLMInvocation) -> str:
    if invocation.agent_id == "gm":
        return "gm"
    if invocation.operation == _EMBED_OPERATION:
        return "embedding"
    return "player-agent"


@dataclass(frozen=True)
class TelemetryTotals:
    """Aggregates for one (agent, role) bucket of the session."""

    key: str
    role: str
    calls: int
    retries: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class InMemoryTelemetrySink:
    """Accumulates records in RAM; snapshot() returns per-(agent, role) totals."""

    def __init__(self) -> None:
        self._records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self._records.append(invocation)

    def snapshot(self) -> tuple[TelemetryTotals, ...]:
        buckets: dict[tuple[str, str], list[LLMInvocation]] = {}
        for record in self._records:
            role = _role_for(record)
            key = record.agent_id if record.agent_id else role
            buckets.setdefault((key, role), []).append(record)
        return tuple(
            TelemetryTotals(
                key=key,
                role=role,
                calls=len(records),
                retries=sum(1 for record in records if record.attempt > 1),
                input_tokens=sum(record.input_tokens or 0 for record in records),
                output_tokens=sum(record.output_tokens or 0 for record in records),
                estimated_cost_usd=sum(
                    record.estimated_cost_usd or 0.0 for record in records
                ),
            )
            for (key, role), records in sorted(buckets.items())
        )
