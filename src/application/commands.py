"""Application commands — statements of intent (CLAUDE.md §12: commands, not events)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.character.abilities import AbilityType
from domain.common.ids import CharacterId, GameId
from domain.rules.ruleset import Ruleset


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
    range_ft: int = 5


def weapon_spec(ruleset: Ruleset, weapon_id: str) -> WeaponSpec:
    """Resolve a ruleset weapon id into the command carry-type (R2 spec §2)."""
    weapon = ruleset.weapon(weapon_id)
    return WeaponSpec(
        weapon_id=weapon.weapon_id,
        name=weapon.name,
        damage_die_count=weapon.damage_die_count,
        damage_die_size=weapon.damage_die_size,
        ability=weapon.ability.value
        if isinstance(weapon.ability, AbilityType)
        else str(weapon.ability),
        range_ft=weapon.range_ft,
    )


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
