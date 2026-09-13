"""Map expected domain/application/model failures to HTTP (contract §3)."""
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ai.models.errors import ModelError
from application.agents.agent_turn_service import AgentNotRegisteredError
from application.gm.director import InvalidGmResponseError
from domain.common.errors import (
    ActionNotAvailableError,
    AgentDecisionFailedError,
    CharacterNotFoundError,
    CombatNotActiveError,
    ConcurrentGameModification,
    DomainError,
    GameNotFoundError,
    GameNotRunningError,
    InsufficientResourceError,
    InvalidActionError,
    NotYourTurnError,
    PersistenceError,
    ValidationError,
)

HANDLER_TABLE: dict[type[Exception], tuple[int, str]] = {
    GameNotFoundError: (404, "game_not_found"),
    CharacterNotFoundError: (404, "character_not_found"),
    ValidationError: (422, "validation_error"),
    InvalidActionError: (422, "invalid_action"),
    InsufficientResourceError: (422, "insufficient_resource"),
    NotYourTurnError: (409, "not_your_turn"),
    ActionNotAvailableError: (409, "action_not_available"),
    CombatNotActiveError: (409, "combat_not_active"),
    GameNotRunningError: (409, "game_not_running"),
    AgentDecisionFailedError: (502, "agent_decision_failed"),
    ConcurrentGameModification: (409, "concurrent_modification"),
    PersistenceError: (503, "persistence_error"),
    ModelError: (502, "model_error"),
    InvalidGmResponseError: (502, "gm_invalid_response"),
    AgentNotRegisteredError: (409, "agent_not_registered"),
}


def _json(status: int, code: str, reason: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "reason": reason})
def register_error_handlers(app: FastAPI) -> None:
    def handler(status: int, code: str) -> Callable[[Request, Exception], Response]:
        def handle(request: Request, exc: Exception) -> Response:
            return _json(status, code, str(exc))

        return handle

    for exc_type, (status, code) in HANDLER_TABLE.items():
        app.add_exception_handler(exc_type, handler(status, code))

    @app.exception_handler(DomainError)
    def unlisted_domain_error(request: Request, exc: DomainError) -> Response:
        return _json(409, "domain_error", str(exc))

    @app.exception_handler(Exception)
    def internal(request: Request, exc: Exception) -> Response:
        return _json(500, "internal_error", "internal server error")
