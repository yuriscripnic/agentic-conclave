"""Session play engine: drive non-player turns and apply human input (spec §4.1)."""

from __future__ import annotations

from dataclasses import dataclass

from application.agents.agent_turn_service import AgentTurnReport
from application.commands import SubmitActionCommand, TravelCommand
from application.gm.director import GmResult
from application.telemetry import new_correlation_id
from application.views import GameView, TurnReport
from domain.common.errors import DomainError
from domain.common.ids import CharacterId
from session.factory import GameSession


@dataclass(frozen=True)
class PendingTurn:
    """One driven non-player turn, ready for the caller to render."""

    kind: str  # "enemy" | "agent"
    turn_report: TurnReport
    agent_report: AgentTurnReport | None = None
    gm_result: GmResult | None = None


@dataclass(frozen=True)
class InputOutcome:
    """The effect of one human input line, for the caller to render."""

    # "empty"|"command"|"unknown"|"attack"|"say"|"travel"|"no_target"
    # "unknown_exit"|"error"
    kind: str
    argument: str = ""
    turn_report: TurnReport | None = None
    gm_result: GmResult | None = None
    error: str | None = None


def parse_input(raw: str) -> tuple[str, str]:
    """Classify one raw input line (moved verbatim from interfaces.cli.app)."""
    stripped = raw.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        return ("command", stripped)
    parts = stripped.split(None, 1)
    if parts[0].lower() == "attack" and len(parts) == 2:
        return ("attack", parts[1].strip())
    if parts[0].lower() == "say" and len(parts) == 2:
        return ("say", parts[1].strip())
    if parts[0].lower() == "go" and len(parts) == 2:
        return ("travel", parts[1].strip())
    return ("unknown", stripped)


def _resolve_target(view: GameView, token: str) -> str | None:
    for member in (*view.party, *view.enemies):
        if member.id == token or member.name.lower() == token.lower():
            return member.id
    return None


def _traveler_id(session: GameSession) -> str | None:
    """The living party member whose move the human controls (first by roster)."""
    view = session.game_service.get_view(session.game_id)
    living = [member for member in view.party if not member.is_defeated]
    return living[0].id if living else None


def _is_enemy(view: GameView, character_id: str) -> bool:
    return any(member.id == character_id for member in view.enemies)


def _gm_react(
    session: GameSession, report: TurnReport, *, correlation_id: str
) -> GmResult | None:
    """React to a finished turn; None when the GM is off or nothing is notable."""
    if session.gm_director is None:
        return None
    return session.gm_director.on_turn_report(
        session.game_id, report, correlation_id=correlation_id
    )


def advance(session: GameSession) -> PendingTurn | None:
    """Drive non-player turns until it is the human's turn or the fight is over.

    Exceptions propagate: the CLI catches DomainError on the agent path exactly
    as today, and the evaluation runner converts them to "error" status.
    """
    service = session.game_service
    view = service.get_view(session.game_id)
    if view.status == "ended":
        return None
    combat = view.combat
    if combat is None or combat.status != "active":
        return None
    actor = combat.active_actor_id
    if actor is None:
        return None
    if _is_enemy(view, actor):
        report = service.run_active_enemy_turns(session.game_id)
        gm_result = _gm_react(session, report, correlation_id=new_correlation_id())
        return PendingTurn(kind="enemy", turn_report=report, gm_result=gm_result)
    if session.turn_service is not None and session.turn_service.is_agent_controlled(
        CharacterId(actor)
    ):
        correlation_id = new_correlation_id()
        agent_report = session.turn_service.take_turn(
            session.game_id, CharacterId(actor), correlation_id=correlation_id
        )
        gm_result = _gm_react(
            session, agent_report.turn_report, correlation_id=correlation_id
        )
        return PendingTurn(
            kind="agent",
            turn_report=agent_report.turn_report,
            agent_report=agent_report,
            gm_result=gm_result,
        )
    return None


def apply_input(session: GameSession, raw: str) -> InputOutcome:
    """Translate one human input into engine work; the caller renders the outcome."""
    kind, argument = parse_input(raw)
    if kind in ("empty", "command", "unknown"):
        return InputOutcome(kind=kind, argument=argument)
    view = session.game_service.get_view(session.game_id)
    if kind == "say":
        if session.gm_director is None:
            return InputOutcome(kind="say", argument=argument)
        gm_result: GmResult | None = session.gm_director.on_player_say(
            session.game_id, argument, correlation_id=new_correlation_id()
        )
        return InputOutcome(kind="say", argument=argument, gm_result=gm_result)
    if kind == "travel":
        actor_id = (
            _traveler_id(session)
        )
        if actor_id is None:
            return InputOutcome(kind="error", argument=argument,
                                error="no living party member to move")
        try:
            report = session.game_service.travel(
                TravelCommand(
                    game_id=session.game_id,
                    actor_id=CharacterId(actor_id),
                    direction=argument,
                )
            )
        except DomainError as error:
            return InputOutcome(kind="error", argument=argument, error=str(error))
        if not report.accepted:
            return InputOutcome(kind="unknown_exit", argument=argument,
                                turn_report=report)
        gm_result = _gm_react(session, report, correlation_id=new_correlation_id())
        return InputOutcome(
            kind="travel", argument=argument, turn_report=report, gm_result=gm_result
        )
    target_id = _resolve_target(view, argument)
    if target_id is None:
        return InputOutcome(kind="no_target", argument=argument)
    actor_id = view.combat.active_actor_id if view.combat else None
    if actor_id is None:
        return InputOutcome(kind="attack", argument=argument)
    try:
        report = session.game_service.submit_action(
            SubmitActionCommand(
                game_id=session.game_id,
                actor_id=CharacterId(actor_id),
                action_type="attack",
                target_id=CharacterId(target_id),
            )
        )
    except DomainError as error:
        return InputOutcome(kind="error", argument=argument, error=str(error))
    gm_result = _gm_react(session, report, correlation_id=new_correlation_id())
    return InputOutcome(
        kind="attack", argument=argument, turn_report=report, gm_result=gm_result
    )