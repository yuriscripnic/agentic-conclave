"""Application commands — statements of intent (CLAUDE.md §12: commands, not events)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.ids import CharacterId, GameId


@dataclass(frozen=True)
class CreateGameCommand:
    campaign_name: str = "The Forgotten Ruins"
    seed: int | None = None


@dataclass(frozen=True)
class WeaponSpec:
    weapon_id: str
    name: str
    damage_die_count: int
    damage_die_size: int
    ability: str = "strength"


@dataclass(frozen=True)
class AddCharacterCommand:
    name: str
    character_type: str = "player"
    character_class: str | None = None
    level: int = 1
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    armor_class: int = 10
    speed_ft: int = 30
    max_hp: int = 1
    weapon: WeaponSpec | None = None


@dataclass(frozen=True)
class SubmitActionCommand:
    game_id: GameId
    actor_id: CharacterId
    action_type: str
    target_id: CharacterId | None = None
    weapon_id: str | None = None


@dataclass(frozen=True)
class TravelCommand:
    game_id: GameId
    actor_id: CharacterId
    direction: str
