"""Retry classification and policy tests (ai.agents)."""

import pytest

from ai.agents.retry import RETRYABLE_MODEL_ERRORS, RetryPolicy, is_retryable
from ai.models.errors import (
    MissingAPIKeyError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    UnsupportedSchemaError,
)


def test_retryable_tuple_is_exactly_the_transient_failures() -> None:
    assert set(RETRYABLE_MODEL_ERRORS) == {
        ModelTimeoutError,
        ModelUnavailableError,
        ModelRateLimitedError,
        ModelInvalidResponseError,
    }


@pytest.mark.parametrize(
    "error",
    [
        ModelTimeoutError("boom"),
        ModelUnavailableError("boom"),
        ModelRateLimitedError("boom"),
        ModelInvalidResponseError("boom"),
    ],
)
def test_is_retryable_true_for_transient_errors(error: Exception) -> None:
    assert is_retryable(error) is True


@pytest.mark.parametrize(
    "error",
    [
        ModelRequestError("bad request"),
        MissingAPIKeyError("no key"),
        UnsupportedSchemaError("bad schema"),
        ValueError("unrelated"),
    ],
)
def test_is_retryable_false_for_non_retryable_errors(error: Exception) -> None:
    assert is_retryable(error) is False


def test_policy_defaults() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.backoff_seconds == 0.0


def test_policy_custom_sleep_is_retained() -> None:
    sleeps: list[float] = []

    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    policy = RetryPolicy(max_attempts=2, backoff_seconds=0.5, sleep=_sleep)
    policy.sleep(0.5)
    assert sleeps == [0.5]


def test_policy_rejects_zero_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_policy_rejects_negative_backoff() -> None:
    with pytest.raises(ValueError, match="backoff_seconds"):
        RetryPolicy(backoff_seconds=-0.1)
