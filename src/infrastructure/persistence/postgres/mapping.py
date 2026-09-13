# src/infrastructure/persistence/postgres/mapping.py
"""Game ↔ row and EventEnvelope ↔ row mapping (spec §6).

Serialization is explicit (no blind asdict): ids become strings, enums their
values. Rebuilding goes through the domain constructors so invalid stored
state fails loudly on load instead of silently propagating. Rows read from
PostgreSQL carry uuid.UUID / datetime values; hand-built dicts carry strings —
both are accepted.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime

from domain.character.abilities import AbilityScores, AbilityType
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.inventory import Inventory, Item
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CampaignId, CharacterId, EventId, GameId, LocationId
from domain.events.collector import EventEnvelope
from domain.world.game import Game, GameStatus


def _require(document: Mapping[str, object], key: str) -> object:
    if key not in document:
        raise ValidationError(f"corrupt persisted state: missing key '{key}'")
    return document[key]


def _as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"corrupt persisted state: {label} must be an integer")
    return value


def _as_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"corrupt persisted state: {label} must be a string")
    return value


def _as_id(value: object, label: str) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    return _as_str(value, label)


def _require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"corrupt persisted state: {label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValidationError(f"corrupt persisted state: {label} must be a list")
    return value


# -- serialization (domain -> row values) ------------------------------------


def _ability_scores_document(scores: AbilityScores) -> dict[str, int]:
    return {
        "strength": scores.strength,
        "dexterity": scores.dexterity,
        "constitution": scores.constitution,
        "intelligence": scores.intelligence,
        "wisdom": scores.wisdom,
        "charisma": scores.charisma,
    }


def _inventory_document(inventory: Inventory) -> dict[str, object]:
    return {
        "gold": inventory.gold,
        "items": {
            item.item_id: {"name": item.name, "quantity": item.quantity}
            for item in inventory.items.values()
        },
    }


def _weapon_document(weapon: Weapon) -> dict[str, object]:
    return {
        "weapon_id": weapon.weapon_id,
        "name": weapon.name,
        "damage_die_count": weapon.damage_die_count,
        "damage_die_size": weapon.damage_die_size,
        "ability": weapon.ability.value,
        "range_ft": weapon.range_ft,
    }


def _character_document(character: Character) -> dict[str, object]:
    return {
        "id": str(character.id),
        "name": character.name,
        "character_type": character.character_type.value,
        "character_class": (
            character.character_class.value if character.character_class else None
        ),
        "level": character.level,
        "ability_scores": _ability_scores_document(character.ability_scores),
        "armor_class": character.armor_class,
        "speed_ft": character.speed_ft,
        "hit_points": {
            "current": character.hit_points.current,
            "maximum": character.hit_points.maximum,
        },
        "conditions": list(character.conditions),
        "inventory": _inventory_document(character.inventory),
        "equipped_weapon": (
            None if character.equipped_weapon is None
            else _weapon_document(character.equipped_weapon)
        ),
    }


def game_to_row(game: Game) -> dict[str, object]:
    """Serialize the aggregate to games-table column values (state = JSONB doc)."""
    return {
        "id": str(game.game_id),
        "campaign_id": str(game.campaign_id),
        "campaign_name": game.campaign_name,
        "seed": game.seed,
        "version": game.version,
        "status": game.status.value,
        "state": {
            "characters": [
                _character_document(character)
                for character in game.characters.values()
            ],
            "party_ids": [str(character_id) for character_id in game.party_ids],
            "enemy_ids": [str(character_id) for character_id in game.enemy_ids],
            "status": game.status.value,
            "placements": {
                str(character_id): str(location_id)
                for character_id, location_id in game.placements.items()
            },
        },
    }


# -- deserialization (row values -> domain) -----------------------------------


def _hit_points_from(document: Mapping[str, object]) -> HitPoints:
    return HitPoints(
        current=_as_int(_require(document, "current"), "hit_points.current"),
        maximum=_as_int(_require(document, "maximum"), "hit_points.maximum"),
    )


def _ability_scores_from(document: Mapping[str, object]) -> AbilityScores:
    return AbilityScores(
        strength=_as_int(_require(document, "strength"), "ability.strength"),
        dexterity=_as_int(_require(document, "dexterity"), "ability.dexterity"),
        constitution=_as_int(
            _require(document, "constitution"), "ability.constitution"
        ),
        intelligence=_as_int(
            _require(document, "intelligence"), "ability.intelligence"
        ),
        wisdom=_as_int(_require(document, "wisdom"), "ability.wisdom"),
        charisma=_as_int(_require(document, "charisma"), "ability.charisma"),
    )


def _inventory_from(document: Mapping[str, object]) -> Inventory:
    items_document = _require_dict(_require(document, "items"), "inventory.items")
    items: dict[str, Item] = {}
    for item_id, entry in items_document.items():
        item_document = _require_dict(entry, f"inventory.items[{item_id}]")
        items[item_id] = Item(
            item_id=item_id,
            name=_as_str(_require(item_document, "name"), "item.name"),
            quantity=_as_int(_require(item_document, "quantity"), "item.quantity"),
        )
    return Inventory(
        items=items, gold=_as_int(_require(document, "gold"), "inventory.gold")
    )


def _weapon_from(document: Mapping[str, object]) -> Weapon:
    ability_value = _as_str(_require(document, "ability"), "weapon.ability")
    try:
        ability = AbilityType(ability_value)
    except ValueError as error:
        raise ValidationError(
            f"corrupt persisted state: unknown ability '{ability_value}'"
        ) from error
    return Weapon(
        weapon_id=_as_str(_require(document, "weapon_id"), "weapon.weapon_id"),
        name=_as_str(_require(document, "name"), "weapon.name"),
        damage_die_count=_as_int(
            _require(document, "damage_die_count"), "weapon.die_count"
        ),
        damage_die_size=_as_int(
            _require(document, "damage_die_size"), "weapon.die_size"
        ),
        ability=ability,
        range_ft=_as_int(_require(document, "range_ft"), "weapon.range_ft"),
    )


def _character_from(document: Mapping[str, object]) -> Character:
    class_value = _require(document, "character_class")
    try:
        character_type = CharacterType(
            _as_str(_require(document, "character_type"), "character.character_type")
        )
        character_class = (
            None
            if class_value is None
            else CharacterClass(_as_str(class_value, "character.character_class"))
        )
    except ValueError as error:
        raise ValidationError(
            f"corrupt persisted state: unknown character enum value: {error}"
        ) from error
    conditions = [
        _as_str(condition, "character.condition")
        for condition in _require_list(
            _require(document, "conditions"), "character.conditions"
        )
    ]
    weapon_value = _require(document, "equipped_weapon")
    return Character(
        id=CharacterId(_as_id(_require(document, "id"), "character.id")),
        name=_as_str(_require(document, "name"), "character.name"),
        character_type=character_type,
        character_class=character_class,
        level=_as_int(_require(document, "level"), "character.level"),
        ability_scores=_ability_scores_from(
            _require_dict(
                _require(document, "ability_scores"), "character.ability_scores"
            )
        ),
        armor_class=_as_int(_require(document, "armor_class"), "character.armor_class"),
        speed_ft=_as_int(_require(document, "speed_ft"), "character.speed_ft"),
        hit_points=_hit_points_from(
            _require_dict(_require(document, "hit_points"), "character.hit_points")
        ),
        conditions=tuple(conditions),
        inventory=_inventory_from(
            _require_dict(_require(document, "inventory"), "character.inventory")
        ),
        equipped_weapon=(
            None
            if weapon_value is None
            else _weapon_from(_require_dict(weapon_value, "character.equipped_weapon"))
        ),
    )


def game_from_row(row: Mapping[str, object]) -> Game:
    """Rebuild the aggregate from column values; ValidationError on any corruption."""
    try:
        return _game_from_row(row)
    except ValidationError as error:
        # Domain constructors raise their own ValidationErrors (e.g. invalid HP);
        # normalize them to the same corruption marker as our structural checks.
        if str(error).startswith("corrupt persisted state"):
            raise
        raise ValidationError(f"corrupt persisted state: {error}") from error


def _game_from_row(row: Mapping[str, object]) -> Game:
    try:
        status = GameStatus(_as_str(_require(row, "status"), "game.status"))
    except ValueError as error:
        raise ValidationError(f"corrupt persisted state: {error}") from error
    state = _require_dict(_require(row, "state"), "game.state")

    characters: dict[CharacterId, Character] = {}
    for entry in _require_list(_require(state, "characters"), "game.state.characters"):
        character = _character_from(_require_dict(entry, "game.state.characters[]"))
        characters[character.id] = character

    game = Game(
        game_id=GameId(_as_id(_require(row, "id"), "game.id")),
        campaign_id=CampaignId(
            _as_id(_require(row, "campaign_id"), "game.campaign_id")
        ),
        campaign_name=_as_str(_require(row, "campaign_name"), "game.campaign_name"),
        seed=_as_int(_require(row, "seed"), "game.seed"),
        characters=characters,
        party_ids=[
            CharacterId(_as_id(value, "game.party_ids[]"))
            for value in _require_list(_require(state, "party_ids"), "game.party_ids")
        ],
        enemy_ids=[
            CharacterId(_as_id(value, "game.enemy_ids[]"))
            for value in _require_list(_require(state, "enemy_ids"), "game.enemy_ids")
        ],
        status=status,
        placements=_placements_from(state),
    )
    game.version = _as_int(_require(row, "version"), "game.version")
    return game


def _placements_from(document: Mapping[str, object]) -> dict[CharacterId, LocationId]:
    """Optional key: older rows (pre-placements) deserialize to {}."""
    raw = document.get("placements")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("corrupt persisted state: game.state.placements")
    return {
        CharacterId(
            _as_id(key, "game.state.placements key")
        ): LocationId(_as_id(value, "game.state.placements value"))
        for key, value in raw.items()
    }


def event_to_row(game_id: GameId, envelope: EventEnvelope) -> dict[str, object]:
    return {
        "game_id": str(game_id),
        "sequence": envelope.sequence,
        "event_id": str(envelope.event_id),
        "occurred_at": envelope.occurred_at,
        "event_type": envelope.event_type,
        "payload": envelope.payload,
    }


def row_to_event(row: Mapping[str, object], game_id: GameId) -> EventEnvelope:
    """Rebuild an envelope; DB rows carry datetime/UUID values, dicts carry strings."""
    occurred_at = _require(row, "occurred_at")
    return EventEnvelope(
        sequence=_as_int(_require(row, "sequence"), "event.sequence"),
        event_id=EventId(_as_id(_require(row, "event_id"), "event.event_id")),
        game_id=game_id,
        occurred_at=(
            occurred_at.isoformat()
            if isinstance(occurred_at, datetime)
            else _as_str(occurred_at, "event.occurred_at")
        ),
        event_type=_as_str(_require(row, "event_type"), "event.event_type"),
        payload=_require_dict(_require(row, "payload"), "event.payload"),
    )
