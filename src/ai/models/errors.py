"""Error taxonomy for the model gateway layer (extends CLAUDE.md §49)."""

from ai.models.types import LLMInvocation


class ModelError(Exception):
    """Base class for model-gateway failures; carries per-call telemetry."""

    def __init__(self, message: str, invocation: LLMInvocation | None = None) -> None:
        super().__init__(message)
        self.invocation = invocation


class ModelTimeoutError(ModelError):
    pass


class ModelRateLimitedError(ModelError):
    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        invocation: LLMInvocation | None = None,
    ) -> None:
        super().__init__(message, invocation)
        self.retry_after_seconds = retry_after_seconds


class ModelRequestError(ModelError):
    pass


class ModelUnavailableError(ModelError):
    pass


class ModelInvalidResponseError(ModelError):
    pass


class MissingAPIKeyError(ModelError):
    pass


class UnsupportedSchemaError(ModelError):
    pass


class ProfileConfigError(ModelError):
    pass


class ProfileNotFoundError(ModelError):
    pass


class InvalidProfileError(ModelError):
    pass


class UnknownProviderError(ModelError):
    pass
