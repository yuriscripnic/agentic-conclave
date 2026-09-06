"""One character agent: identity, prompts, and structured-decision mapping."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from application.agents.party_board import PartyMessage
from application.agents.perception import AgentPerception
from application.agents.profiles import AgentProfile
from domain.common.ids import CharacterId
from domain.rules.actions import AttackProposal

ATTACK_DECISION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["attack"]},
        "target_id": {"type": "string"},
        "public_message": {"type": "string"},
        "party_message": {"type": "string"},
    },
    "required": ["action_type", "target_id", "public_message"],
    "additionalProperties": False,
}

_PARTY_MESSAGE_MAX_CHARS = 200


class InvalidAgentDecisionError(ValueError):
    """The model's decision failed agent-level mapping (unknown/dead target, bad fields)."""


@dataclass(frozen=True)
class AgentDecision:
    proposal: AttackProposal
    public_message: str
    party_message: str | None = None


class CharacterAgent:
    """Prompt construction and decision mapping for one agent-controlled character."""

    def __init__(self, profile: AgentProfile) -> None:
        self._profile = profile

    def build_system_prompt(self) -> str:
        return (
            f"You are {self._profile.character_name}, a {self._profile.character_class} "
            "in a tabletop role-playing combat.\n"
            f"Personality: {self._profile.persona}\n"
            f"Objective: {self._profile.objective}\n"
            "\n"
            "Rules:\n"
            "- You may only take the attack action.\n"
            "- Choose exactly one target_id from the opponents listed in the user message.\n"
            "- You may include party_message: one short sentence coordinating with your "
            "allies. Omit it to stay silent.\n"
            '- Reply ONLY with a JSON object: action_type ("attack"), target_id (string), '
            "public_message (a short first-person battle cry or rationale; never hidden "
            "reasoning), and optionally party_message (one short sentence for your allies).\n"
            "- No other keys, no prose outside the JSON."
        )

    def build_user_prompt(
        self,
        perception: AgentPerception,
        *,
        rejection: str | None = None,
        party_messages: tuple[PartyMessage, ...] = (),
    ) -> str:
        me = perception.self_view
        conditions = ", ".join(me.conditions) if me.conditions else "none"
        lines = [
            f"Round {perception.round_number}. It is your turn.",
            f"You: {me.name} (level {me.level}, {me.character_class}), "
            f"HP {me.hp_current}/{me.hp_max}, AC {me.armor_class}, "
            f"conditions: {conditions}.",
            "Opponents:",
        ]
        lines.extend(
            f"- {opponent.id}: {opponent.name} "
            f"({'defeated' if opponent.is_defeated else 'standing'})"
            for opponent in perception.opponents
        )
        if party_messages:
            lines.append("Party chatter:")
            lines.extend(
                f"- {message.actor_name} (round {message.round_number}): {message.text}"
                for message in party_messages
            )
        lines.append(f"Turn order: {', '.join(perception.initiative_order)}")
        if rejection is not None:
            lines.append(f"Your previous action was rejected: {rejection}. Choose again.")
        return "\n".join(lines)

    def map_decision(
        self, data: Mapping[str, Any], perception: AgentPerception
    ) -> AgentDecision:
        if data.get("action_type") != "attack":
            raise InvalidAgentDecisionError(
                f"unsupported action_type: {data.get('action_type')!r}"
            )

        target_id = data.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            raise InvalidAgentDecisionError("target_id must be a non-empty string")

        living = {
            opponent.id: opponent
            for opponent in perception.opponents
            if not opponent.is_defeated
        }
        if target_id not in living:
            raise InvalidAgentDecisionError(
                f"target '{target_id}' is not a living opponent (living: {sorted(living)})"
            )

        public_message = data.get("public_message")
        if not isinstance(public_message, str) or not public_message.strip():
            raise InvalidAgentDecisionError("public_message must be a non-empty string")

        return AgentDecision(
            proposal=AttackProposal(
                actor_id=CharacterId(perception.active_actor_id),
                target_id=CharacterId(target_id),
            ),
            public_message=public_message.strip(),
            party_message=self._map_party_message(data.get("party_message")),
        )

    @staticmethod
    def _map_party_message(raw: object) -> str | None:
        """Chatter is cosmetic: never a rejection — silence, collapse, truncate (spec §3.4)."""
        if not isinstance(raw, str):
            return None
        collapsed = " ".join(raw.split())
        if not collapsed:
            return None
        return collapsed[:_PARTY_MESSAGE_MAX_CHARS]
