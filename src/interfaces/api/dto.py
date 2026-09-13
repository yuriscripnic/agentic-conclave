"""HTTP DTOs: pydantic models mirroring application views field-for-field.

Contract: docs/architecture/domain-model-and-api.md §1 — domain objects never
cross the wire (CLAUDE.md §41).
"""
from pydantic import BaseModel

from application.gm.director import GmResult
from application.views import CombatView, GameView, TurnReport
from domain.events.collector import EventEnvelope


class CharacterResponse(BaseModel):
    id: str
    name: str
    character_class: str | None
    level: int
    hp_current: int
    hp_max: int
    armor_class: int
    conditions: list[str]
    is_defeated: bool


class InitiativeEntryResponse(BaseModel):
    character_id: str
    name: str
    total: int


class CombatResponse(BaseModel):
    round_number: int
    status: str
    active_actor_id: str | None
    initiative_order: list[InitiativeEntryResponse]


class GameViewResponse(BaseModel):
    game_id: str
    campaign_name: str
    status: str
    party: list[CharacterResponse]
    enemies: list[CharacterResponse]
    combat: CombatResponse | None


class EventEnvelopeResponse(BaseModel):
    sequence: int
    event_id: str
    game_id: str
    occurred_at: str
    event_type: str
    payload: dict[str, object]


class TurnReportResponse(BaseModel):
    game_id: str
    accepted: bool
    error_code: str
    reason: str
    events: list[EventEnvelopeResponse]
    view: GameViewResponse
    game_over: bool


class StatusResponse(BaseModel):
    status: str
    combat: CombatResponse | None
    game_over: bool


class GmResponse(BaseModel):
    narration: str | None
    npc_reply: str | None
    addressed_to: str | None


class SessionResponse(BaseModel):
    game_id: str
    view: GameViewResponse
    opening: GmResponse | None


def game_view_response(view: GameView) -> GameViewResponse:
    return GameViewResponse.model_validate(view, from_attributes=True)


def event_response(envelope: EventEnvelope) -> EventEnvelopeResponse:
    return EventEnvelopeResponse(
        sequence=envelope.sequence,
        event_id=str(envelope.event_id),
        game_id=str(envelope.game_id),
        occurred_at=envelope.occurred_at,
        event_type=envelope.event_type,
        payload=dict(envelope.payload),
    )


def turn_report_response(report: TurnReport) -> TurnReportResponse:
    return TurnReportResponse(
        game_id=report.game_id,
        accepted=report.accepted,
        error_code=report.error_code,
        reason=report.reason,
        events=[event_response(event) for event in report.events],
        view=game_view_response(report.view),
        game_over=report.game_over,
    )


def combat_response(combat: CombatView) -> CombatResponse:
    return CombatResponse.model_validate(combat, from_attributes=True)


def status_response(view: GameView) -> StatusResponse:
    combat = view.combat
    game_over = combat is not None and combat.status == "ended" or view.status == "ended"
    return StatusResponse(
        status=view.status,
        combat=combat_response(combat) if combat is not None else None,
        game_over=game_over,
    )


def gm_response(result: GmResult | None) -> GmResponse | None:
    if result is None:
        return None
    return GmResponse(
        narration=result.narration,
        npc_reply=result.npc_reply,
        addressed_to=result.addressed_to,
    )
