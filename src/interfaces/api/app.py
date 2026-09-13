"""HTTP adapter over the session/application layer (Phase 19).

Contract: docs/architecture/domain-model-and-api.md. Routes validate HTTP
input, build commands, call the composition root / application services, and
map results to DTOs — no game rules live here (CLAUDE.md §40).
"""
import secrets
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from interfaces.api.dto import (
    EventEnvelopeResponse,
    GameViewResponse,
    SessionResponse,
    StatusResponse,
    event_response,
    game_view_response,
    gm_response,
    status_response,
)
from interfaces.api.store import IdempotencyStore, SessionRegistry
from session.factory import SessionConfig

SCOPE_CREATE_GAMES = "POST /games"


class CreateGameRequest(BaseModel):
    campaign_name: str = "The Forgotten Ruins"
    seed: int | None = None


def create_app(*, agent_mode: str = "llm", gm_mode: str = "off") -> FastAPI:
    """Compose the API; modes come from the caller (CLI/env config, tests pass `fake`)."""
    app = FastAPI(title="Agentic Conclave API", version="0.1.0")
    app.state.agent_mode = agent_mode
    app.state.gm_mode = gm_mode
    registry = SessionRegistry(agent_mode=agent_mode, gm_mode=gm_mode)
    idempotency = IdempotencyStore()

    def _idempotent(
        request: Request,
        scope: str,
        success_status: int,
        build: Callable[[], BaseModel],
    ) -> Response:
        """Return the first response for an Idempotency-Key, else compute and cache."""
        key = request.headers.get("Idempotency-Key", "")
        cached = idempotency.response_or(key, scope)
        if cached is not None:
            return JSONResponse(cached, status_code=success_status)
        body = build()
        idempotency.remember(key, scope, body.model_dump())
        return JSONResponse(body.model_dump(), status_code=success_status)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/games")
    def create_game(create_request: CreateGameRequest, http_request: Request) -> Response:
        def build() -> SessionResponse:
            seed = create_request.seed if create_request.seed is not None else secrets.randbits(32)
            config = SessionConfig(
                seed=seed,
                agent_mode=agent_mode,
                gm_mode=gm_mode,
            )
            game_id = registry.build(config)
            session = registry.get(game_id)
            view = game_view_response(session.game_service.get_view(session.game_id))
            opening = gm_response(session.opening)
            return SessionResponse(game_id=game_id, view=view, opening=opening)

        return _idempotent(http_request, SCOPE_CREATE_GAMES, 201, build)

    @app.get("/api/v1/games/{game_id}")
    def get_game(game_id: str) -> GameViewResponse:
        session = registry.get(game_id)
        return game_view_response(session.game_service.get_view(session.game_id))

    @app.get("/api/v1/games/{game_id}/status")
    def get_status(game_id: str) -> StatusResponse:
        session = registry.get(game_id)
        return status_response(session.game_service.get_view(session.game_id))

    @app.get("/api/v1/games/{game_id}/events")
    def get_events(game_id: str) -> dict[str, list[EventEnvelopeResponse]]:
        session = registry.get(game_id)
        events = session.game_service.get_events(session.game_id)
        return {"events": [event_response(event) for event in events]}

    return app
