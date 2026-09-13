"""Read models for interfaces — never leak domain objects (CLAUDE.md §41)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.events.collector import EventEnvelope


@dataclass(frozen=True)
class CharacterView:
    id: str
    name: str
    character_class: str | None
    level: int
    hp_current: int
    hp_max: int
    armor_class: int
    conditions: list[str]
    is_defeated: bool


@dataclass(frozen=True)
class InitiativeEntryView:
    character_id: str
    name: str
    total: int


@dataclass(frozen=True)
class CombatView:
    round_number: int
    status: str
    active_actor_id: str | None
    initiative_order: list[InitiativeEntryView]


@dataclass(frozen=True)
class SceneView:
    location_id: str
    name: str
    description: str
    exits: list[tuple[str, str]]


@dataclass(frozen=True)
class GameView:
    game_id: str
    campaign_name: str
    status: str
    party: list[CharacterView]
    enemies: list[CharacterView]
    combat: CombatView | None
    scene: SceneView | None = None


@dataclass(frozen=True)
class TurnReport:
    game_id: str
    accepted: bool
    error_code: str
    reason: str
    events: list[EventEnvelope]
    view: GameView
    game_over: bool
