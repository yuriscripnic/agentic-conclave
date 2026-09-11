"""Combat state: initiative, rounds, turns (Implementation Plan §8)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from domain.character.abilities import AbilityType
from domain.character.character import Character
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId
from domain.rules.actions import ActionEconomy
from domain.rules.dice import DiceRoller


class CombatStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


@dataclass(frozen=True)
class InitiativeEntry:
    character_id: CharacterId
    total: int
    dexterity_modifier: int
    tiebreaker: int


def roll_initiative(
    dice: DiceRoller,
    characters: dict[CharacterId, Character],
    participant_ids: Sequence[CharacterId],
) -> list[InitiativeEntry]:
    entries: list[InitiativeEntry] = []
    for character_id in participant_ids:
        character = characters[character_id]
        dex_modifier = character.ability_scores.modifier(AbilityType.DEXTERITY)
        natural = dice.roll_d20().natural
        if natural is None:  # pragma: no cover - roll_d20 always yields a natural
            raise ValidationError("initiative requires a single d20 roll")
        entries.append(
            InitiativeEntry(
                character_id=character_id,
                total=natural + dex_modifier,
                dexterity_modifier=dex_modifier,
                tiebreaker=natural,
            )
        )
    # Ties on (total, dexterity modifier) keep participant order: the sort is
    # stable, so no random id is needed as a tiebreak (§47 reproducibility).
    entries.sort(key=lambda entry: (-entry.total, -entry.dexterity_modifier))
    return entries


@dataclass
class Combat:
    entries: list[InitiativeEntry]
    economy: ActionEconomy
    round_number: int = 1
    turn_index: int = 0
    status: CombatStatus = CombatStatus.ACTIVE

    def active_actor(self) -> CharacterId:
        return self.entries[self.turn_index].character_id
