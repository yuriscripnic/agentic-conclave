"""Typed MVP-0 events (Implementation Plan §9)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.ids import CampaignId, CharacterId
from domain.events.base import BaseEvent


@dataclass(frozen=True)
class GameCreated(BaseEvent):
    campaign_id: CampaignId
    seed: int


@dataclass(frozen=True)
class GameStarted(BaseEvent):
    pass


@dataclass(frozen=True)
class InitiativeRolled(BaseEvent):
    character_id: CharacterId
    total: int


@dataclass(frozen=True)
class CombatStarted(BaseEvent):
    participant_ids: tuple[CharacterId, ...]
    round_number: int


@dataclass(frozen=True)
class TurnStarted(BaseEvent):
    round_number: int
    actor_id: CharacterId


@dataclass(frozen=True)
class TurnEnded(BaseEvent):
    round_number: int
    actor_id: CharacterId


@dataclass(frozen=True)
class AttackRequested(BaseEvent):
    attacker_id: CharacterId
    target_id: CharacterId
    weapon_id: str


@dataclass(frozen=True)
class AttackResolved(BaseEvent):
    attacker_id: CharacterId
    target_id: CharacterId
    roll: int
    attack_bonus: int
    total: int
    target_ac: int
    hit: bool
    critical: bool


@dataclass(frozen=True)
class DamageApplied(BaseEvent):
    character_id: CharacterId
    amount: int
    hp_before: int
    hp_after: int


@dataclass(frozen=True)
class CharacterDefeated(BaseEvent):
    character_id: CharacterId


@dataclass(frozen=True)
class ActionRejected(BaseEvent):
    actor_id: CharacterId
    action_type: str
    reason: str


@dataclass(frozen=True)
class CombatEnded(BaseEvent):
    winner_side: str
    round_number: int
