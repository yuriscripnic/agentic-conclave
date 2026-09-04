"""Deterministic MVP-0 enemy behaviour (Implementation Plan §8)."""

from __future__ import annotations

from domain.common.errors import AgentDecisionFailedError
from domain.common.ids import CharacterId
from domain.rules.actions import AttackProposal
from domain.world.game import Game


class SimpleMeleeEnemyPolicy:
    """Attack the first living opponent; deterministic, no LLM."""

    def decide(self, game: Game, actor_id: CharacterId) -> AttackProposal:
        for opponent_id in game.opponents_of(actor_id):
            if not game.characters[opponent_id].is_defeated():
                return AttackProposal(actor_id=actor_id, target_id=opponent_id)
        raise AgentDecisionFailedError(f"{actor_id} has no living opponents to attack")
