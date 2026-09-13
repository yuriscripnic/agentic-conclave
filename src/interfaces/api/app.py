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

from application.commands import SubmitActionCommand
from application.views import GameView
from domain.common.errors import (
    CharacterNotFoundError,
    CombatNotActiveError,
)
from domain.common.ids import CharacterId
from interfaces.api.dto import (
    EventEnvelopeResponse,
    GameViewResponse,
    InputResponse,
    SessionResponse,
    StatusResponse,
    TurnReportResponse,
    event_response,
    game_view_response,
    gm_response,
    status_response,
    turn_report_response,
)
from interfaces.api.errors import register_error_handlers
from interfaces.api.store import IdempotencyStore, SessionRegistry
from interfaces.web.mount import mount_web
from session.factory import GameSession, SessionConfig
from session.play import advance, apply_input

SCOPE_CREATE_GAMES = "POST /games"


class CreateGameRequest(BaseModel):
    campaign_name: str = "The Forgotten Ruins"
    seed: int | None = None


class ActionRequest(BaseModel):
    action_type: str
    target: str | None = None  # id or case-insensitive name, CLI-style
    weapon_id: str | None = None


class InputRequest(BaseModel):
    text: str


def resolve_target(game_view: GameView, raw: str) -> str:
    """Resolve a target by id or case-insensitive name across party and enemies."""
    for member in (*game_view.party, *game_view.enemies):
        if member.id == raw or member.name.lower() == raw.lower():
            return member.id
    raise CharacterNotFoundError(f"target not found: {raw!r}")


def active_actor_id(game_view: GameView) -> CharacterId:
    """The actor whose turn it is; combat must be active."""
    if game_view.combat is None:
        raise CombatNotActiveError("combat has not started for this game")
    if game_view.combat.active_actor_id is None:
        raise CombatNotActiveError("combat has ended; no active actor")
    return CharacterId(game_view.combat.active_actor_id)


def create_app(*, agent_mode: str = "llm", gm_mode: str = "off") -> FastAPI:
    """Compose the API; modes come from the caller (CLI/env config, tests pass `fake`)."""
    app = FastAPI(title="Agentic Conclave API", version="0.1.0")
    app.state.agent_mode = agent_mode
    app.state.gm_mode = gm_mode
    registry = SessionRegistry(agent_mode=agent_mode, gm_mode=gm_mode)
    idempotency = IdempotencyStore()

    def drive_non_players(session: GameSession) -> None:
        """Run agent/enemy turns until the human acts (session.play.advance loop)."""
        while advance(session) is not None:
            pass

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

    @app.post("/api/v1/games/{game_id}/actions")
    def submit_action(game_id: str, action: ActionRequest, http_request: Request) -> Response:
        def build() -> TurnReportResponse:
            session = registry.get(game_id)
            with registry.lock_for(game_id):
                drive_non_players(session)
                view = session.game_service.get_view(session.game_id)
                target_id = resolve_target(view, action.target) if action.target else None
                report = session.game_service.submit_action(
                    SubmitActionCommand(
                        game_id=session.game_id,
                        actor_id=active_actor_id(view),
                        action_type=action.action_type,
                        target_id=CharacterId(target_id) if target_id else None,
                        weapon_id=action.weapon_id,
                    )
                )
            return turn_report_response(report)

        return _idempotent(http_request, f"games/{game_id}/actions", 200, build)

    @app.post("/api/v1/games/{game_id}/input")
    def submit_input(game_id: str, input_request: InputRequest, http_request: Request) -> Response:
        def build() -> InputResponse:
            session = registry.get(game_id)
            with registry.lock_for(game_id):
                drive_non_players(session)
                outcome = apply_input(session, input_request.text)
            return InputResponse(
                kind=outcome.kind,
                report=turn_report_response(outcome.turn_report)
                if outcome.turn_report is not None
                else None,
                gm=gm_response(outcome.gm_result),
            )

        return _idempotent(http_request, f"games/{game_id}/input", 200, build)

    register_error_handlers(app)
    mount_web(app)
    return app
