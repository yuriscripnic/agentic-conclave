"""Value types shared by every ModelGateway implementation."""

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[Message, ...]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class LLMInvocation:
    """Per-call telemetry metadata (CLAUDE.md §34). Never prompts, payloads, or reasoning."""

    provider: str
    model: str
    operation: str
    status: str
    error_kind: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    request_id: str


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str
    usage: Usage
    finish_reason: str
    invocation: LLMInvocation


@dataclass(frozen=True)
class StructuredModelResponse:
    data: dict[str, Any]
    model: str
    usage: Usage
    finish_reason: str
    invocation: LLMInvocation
