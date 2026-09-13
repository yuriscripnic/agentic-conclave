"""Out-of-combat scene decision schema, mapping, and validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from domain.common.ids import CharacterId, EntityId
from domain.world.game import Game
from domain.world.locations import WorldMap

SCENE_DECISION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["talk", "travel", "wait"]},
        "speech": {"type": "string"},
        "exit_direction": {"type": "string"},
        "public_message": {"type": "string"},
    },
    "required": ["action_type", "public_message"],
    "additionalProperties": False,
}


class InvalidSceneDecisionError(ValueError):
    """The model's scene decision failed agent-level mapping or validation."""


@dataclass(frozen=True)
class SceneDecision:
    action_type: str  # "talk" | "travel" | "wait"
    public_message: str
    speech: str | None = None
    exit_direction: str | None = None


def map_scene_decision(data: Mapping[str, object]) -> SceneDecision:
    """Map a validated structured output to a SceneDecision."""
    action_type = data.get("action_type")
    if not isinstance(action_type, str):
        raise InvalidSceneDecisionError("scene decision needs a string action_type")
    if action_type not in ("talk", "travel", "wait"):
        raise InvalidSceneDecisionError(f"unknown scene action_type: {action_type}")
    public_message = data.get("public_message")
    if not isinstance(public_message, str):  # schema requires it, belts and braces
        raise InvalidSceneDecisionError("scene decision needs a public_message")
    speech = data.get("speech")
    exit_direction = data.get("exit_direction")
    if action_type == "talk" and not (isinstance(speech, str) and speech):
        raise InvalidSceneDecisionError("a talk decision needs speech text")
    if action_type == "travel" and not (
        isinstance(exit_direction, str) and exit_direction
    ):
        raise InvalidSceneDecisionError("a travel decision needs exit_direction")
    return SceneDecision(
        action_type=action_type,
        public_message=public_message,
        speech=speech if isinstance(speech, str) else None,
        exit_direction=exit_direction if isinstance(exit_direction, str) else None,
    )


def validate_scene_decision(
    decision: SceneDecision,
    game: Game,
    world: WorldMap,
    actor_id: str | CharacterId,
) -> str | None:
    """Rule-adjacent feasibility check; None is legal, else the rejection reason.

    Deterministic only: shape logic (exit keys, aliveness). Legality (combat,
    placement) is re-checked by the engine when executing the proposal.
    """
    actor: CharacterId = (
        CharacterId(actor_id.value)
        if isinstance(actor_id, EntityId)
        else CharacterId(actor_id)
    )
    if actor not in game.characters:
        return "unknown_character"
    if actor not in game.living_party_ids:
        return "unknown_character"
    if decision.action_type == "talk" and not decision.speech:
        return "talk_needs_speech"
    if decision.action_type == "travel":
        here = game.location_of(actor)
        if here is None:
            return "unknown_exit"
        if world.get(here).is_exit_to(decision.exit_direction or "") is None:
            return "unknown_exit"
    return None
