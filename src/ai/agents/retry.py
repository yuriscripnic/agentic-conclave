"""Transport-retry policy for agent decisions (keyed off exception types)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ai.models.errors import (
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelTimeoutError,
    ModelUnavailableError,
)

RETRYABLE_MODEL_ERRORS: tuple[type[ModelError], ...] = (
    ModelTimeoutError,
    ModelUnavailableError,
    ModelRateLimitedError,
    ModelInvalidResponseError,
)


def is_retryable(exc: BaseException) -> bool:
    """True exactly for the transient failure types in RETRYABLE_MODEL_ERRORS."""
    return isinstance(exc, RETRYABLE_MODEL_ERRORS)


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry budget for one decision request (same request re-sent)."""

    max_attempts: int = 3
    backoff_seconds: float = 0.0
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")
