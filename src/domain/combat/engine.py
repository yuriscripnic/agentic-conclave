"""Deterministic combat engine — validates proposals, resolves attacks, emits events."""

from __future__ import annotations

from collections.abc import Sequence

from domain.combat.state import Combat, CombatStatus, roll_initiative
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId
from domain.events.collector import EventCollector
from domain.events.events import (
    ActionRejected,
    AttackRequested,
    AttackResolved,
    CharacterDefeated,
    CombatEnded,
    CombatStarted,
    DamageApplied,
    InitiativeRolled,
    TurnEnded,
    TurnStarted,
)
from domain.rules.actions import (
    ActionEconomy,
    ActionType,
    AttackProposal,
    ValidationResult,
)
from domain.rules.checks import CheckResolver
from domain.rules.dice import DiceRoller
from domain.rules.progression import proficiency_bonus
from domain.space.board import Board, CoverLevel, Spawns
from domain.space.geometry import cover_between, distance_ft, line_of_sight
from domain.space.square import Square
from domain.world.game import Game


def _positions_for(
    game: Game,
    board: Board | None,
    spawns: Spawns | None,
    participant_ids: Sequence[CharacterId],
) -> dict[CharacterId, Square]:
    """Positions for a fight: empty without a board, assigned from spawns otherwise."""
    if board is None:
        return {}
    if spawns is None:
        raise ValidationError("a board requires spawn squares")
    return _assign_positions(game, board, spawns, participant_ids)


def _assign_positions(
    game: Game,
    board: Board,
    spawns: Spawns,
    participant_ids: Sequence[CharacterId],
) -> dict[CharacterId, Square]:
    """Spawn squares are content: assign in list order, reject any gap or clash.

    Capacity is checked against the participants actually taking part in the
    fight (spec §4), not the whole game roster: a campaign may hold members who
    are absent from this encounter.
    """
    participants = set(participant_ids)
    party = [cid for cid in game.party_ids if cid in participants]
    enemies = [cid for cid in game.enemy_ids if cid in participants]
    if len(party) + len(enemies) != len(participants):
        raise ValidationError("every participant must be on the party or enemy roster")
    if len(party) > len(spawns.party) or len(enemies) > len(spawns.enemies):
        raise ValidationError("not enough spawn squares for every participant")
    positions: dict[CharacterId, Square] = {}
    for character_id, square in zip(party, spawns.party, strict=False):
        positions[character_id] = square
    for character_id, square in zip(enemies, spawns.enemies, strict=False):
        positions[character_id] = square
    if len(set(positions.values())) != len(positions):
        raise ValidationError("spawn squares must be distinct")
    for square in positions.values():
        if not board.in_bounds(square) or board.is_wall(square):
            raise ValidationError(f"spawn square {square} is not a standing square")
    return positions


class CombatEngine:
    def __init__(self, dice: DiceRoller, diagonal_rule: str = "5_10_5") -> None:
        self._dice = dice
        self._diagonal_rule = diagonal_rule
        self._checks = CheckResolver(dice)

    def start(
        self,
        game: Game,
        participant_ids: Sequence[CharacterId],
        collector: EventCollector,
        board: Board | None = None,
        spawns: Spawns | None = None,
    ) -> Combat:
        entries = roll_initiative(self._dice, game.characters, participant_ids)
        for entry in entries:
            collector.record(
                InitiativeRolled(character_id=entry.character_id, total=entry.total)
            )
        first = entries[0].character_id
        combat = Combat(
            entries=entries,
            economy=ActionEconomy(movement_budget_ft=game.characters[first].speed_ft),
            board=board,
            positions=_positions_for(game, board, spawns, participant_ids),
        )
        collector.record(
            CombatStarted(
                participant_ids=tuple(participant_ids),
                round_number=combat.round_number,
            )
        )
        collector.record(TurnStarted(round_number=combat.round_number, actor_id=first))
        return combat

    def validate(
        self, game: Game, combat: Combat, proposal: AttackProposal
    ) -> ValidationResult:
        if combat.status is not CombatStatus.ACTIVE:
            return ValidationResult.reject("combat is not active", "combat_not_active")
        if proposal.actor_id != combat.active_actor():
            return ValidationResult.reject(
                f"it is not {proposal.actor_id}'s turn", "not_your_turn"
            )
        actor = game.characters.get(proposal.actor_id)
        if actor is None or actor.is_defeated():
            return ValidationResult.reject("actor cannot act", "not_your_turn")
        if not combat.economy.can_take_action(ActionType.ATTACK):
            return ValidationResult.reject(
                "the action is no longer available this turn", "action_unavailable"
            )
        if actor.equipped_weapon is None:
            return ValidationResult.reject("no weapon is equipped", "invalid_action")
        weapon = actor.equipped_weapon
        if proposal.weapon_id is not None and (
            proposal.weapon_id != actor.equipped_weapon.weapon_id
        ):
            return ValidationResult.reject(
                "requested weapon is not available", "invalid_action"
            )
        target = game.characters.get(proposal.target_id)
        if target is None or target.id == actor.id or target.is_defeated():
            return ValidationResult.reject("invalid target", "invalid_target")
        if game.side_of(target.id) == game.side_of(actor.id):
            return ValidationResult.reject(
                "cannot attack a member of your own side", "invalid_target"
            )
        board = combat.board
        if board is None:
            return ValidationResult.ok()
        if target.id not in combat.positions:
            return ValidationResult.reject(
                "target is not part of this encounter", "invalid_target"
            )
        actor_square = combat.positions[actor.id]
        target_square = combat.positions[target.id]
        if (
            distance_ft(actor_square, target_square, diagonal_rule=self._diagonal_rule)
            > weapon.range_ft
        ):
            return ValidationResult.reject("target is out of range", "out_of_range")
        if not line_of_sight(board, actor_square, target_square):
            return ValidationResult.reject(
                "no line of sight to target", "no_line_of_sight"
            )
        if cover_between(board, actor_square, target_square) is CoverLevel.TOTAL:
            return ValidationResult.reject("target has total cover", "total_cover")
        return ValidationResult.ok()

    def resolve(
        self,
        game: Game,
        combat: Combat,
        proposal: AttackProposal,
        collector: EventCollector,
    ) -> ValidationResult:
        result = self.validate(game, combat, proposal)
        if not result.valid:
            collector.record(
                ActionRejected(
                    actor_id=proposal.actor_id,
                    action_type=proposal.action_type.value,
                    reason=result.reason,
                )
            )
            return result

        actor = game.characters[proposal.actor_id]
        target = game.characters[proposal.target_id]
        weapon = actor.equipped_weapon
        if weapon is None:  # pragma: no cover - validate guarantees a weapon
            return ValidationResult.reject("no weapon is equipped", "invalid_action")

        collector.record(
            AttackRequested(
                attacker_id=actor.id, target_id=target.id, weapon_id=weapon.weapon_id
            )
        )
        attack_bonus = (
            actor.ability_scores.modifier(weapon.ability) + proficiency_bonus(actor.level)
        )
        target_ac = target.armor_class
        if combat.board is not None:
            cover = cover_between(
                combat.board,
                combat.positions[actor.id],
                combat.positions[target.id],
            )
            if cover is CoverLevel.HALF:
                target_ac += 2
            elif cover is CoverLevel.THREE_QUARTERS:
                target_ac += 5
        roll = self._checks.attack_roll(attack_bonus, target_ac)
        collector.record(
            AttackResolved(
                attacker_id=actor.id,
                target_id=target.id,
                roll=roll.roll,
                attack_bonus=attack_bonus,
                total=roll.total,
                target_ac=roll.target_ac,
                hit=roll.hit,
                critical=roll.is_critical,
            )
        )
        combat.economy.use(ActionType.ATTACK)
        if not roll.hit:
            return result

        die_count = (
            weapon.damage_die_count * 2 if roll.is_critical else weapon.damage_die_count
        )
        damage = max(
            0,
            self._dice.roll(
                die_count,
                weapon.damage_die_size,
                modifier=actor.ability_scores.modifier(weapon.ability),
            ).total,
        )
        hp_before = target.hit_points.current
        target.apply_damage(damage)
        collector.record(
            DamageApplied(
                character_id=target.id,
                amount=damage,
                hp_before=hp_before,
                hp_after=target.hit_points.current,
            )
        )
        if target.is_defeated():
            collector.record(CharacterDefeated(character_id=target.id))
        return result

    def advance_turn(
        self, game: Game, combat: Combat, collector: EventCollector
    ) -> None:
        if combat.status is not CombatStatus.ACTIVE:
            return
        collector.record(
            TurnEnded(round_number=combat.round_number, actor_id=combat.active_actor())
        )
        if not game.living_enemy_ids:
            self._end(combat, collector, winner_side="party")
            return
        if not game.living_party_ids:
            self._end(combat, collector, winner_side="enemies")
            return

        count = len(combat.entries)
        for step in range(1, count + 1):
            index = (combat.turn_index + step) % count
            candidate = combat.entries[index].character_id
            if game.characters[candidate].is_defeated():
                continue
            if index <= combat.turn_index:
                combat.round_number += 1
            combat.turn_index = index
            combat.economy = ActionEconomy(
                movement_budget_ft=game.characters[candidate].speed_ft
            )
            collector.record(
                TurnStarted(round_number=combat.round_number, actor_id=candidate)
            )
            return

    def _end(self, combat: Combat, collector: EventCollector, winner_side: str) -> None:
        combat.status = CombatStatus.ENDED
        collector.record(
            CombatEnded(winner_side=winner_side, round_number=combat.round_number)
        )
