"""CharacterAgent prompt and decision-mapping tests."""

from typing import Any

import pytest

from ai.models.errors import ModelInvalidResponseError
from ai.models.schema import validate_against_schema
from application.agents.character_agent import (
    ATTACK_DECISION_SCHEMA,
    CharacterAgent,
    InvalidAgentDecisionError,
)
from application.agents.perception import AgentPerception, OpponentBrief
from application.agents.profiles import AgentProfile
from application.views import CharacterView
from domain.common.ids import CharacterId

_PROFILE = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword who prefers finishing fights quickly and safely.",
    objective="Survive the skirmish and protect Arin; engage the nearest threat.",
    model_profile="player",
)


def _perception(**overrides: Any) -> AgentPerception:
    me = CharacterView(
        id="brix",
        name="Brix",
        character_class="fighter",
        level=1,
        hp_current=10,
        hp_max=12,
        armor_class=16,
        conditions=[],
        is_defeated=False,
    )
    values: dict[str, Any] = {
        "round_number": 2,
        "active_actor_id": "brix",
        "self_view": me,
        "opponents": (
            OpponentBrief(id="gob", name="Goblin", is_defeated=False),
            OpponentBrief(id="orc", name="Orc", is_defeated=True),
        ),
        "initiative_order": ("Brix", "Goblin", "Arin"),
    }
    values.update(overrides)
    return AgentPerception(**values)


def test_system_prompt_carries_persona_objective_and_rules() -> None:
    prompt = CharacterAgent(_PROFILE).build_system_prompt()
    assert "Brix" in prompt
    assert "cautious sellsword" in prompt
    assert "protect Arin" in prompt
    assert "attack" in prompt
    assert "target_id" in prompt


def test_user_prompt_lists_opponents_but_never_enemy_hp() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception())
    assert "- gob: Goblin (standing)" in prompt
    assert "- orc: Orc (defeated)" in prompt
    assert "HP 10/12" in prompt
    assert prompt.count("HP") == 1  # own HP line only — no enemy HP anywhere
    assert prompt.count("AC") == 1  # own AC line only — no enemy AC anywhere
    assert "Turn order: Brix, Goblin, Arin" in prompt


def test_rejection_feedback_is_appended() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(
        _perception(), rejection="target 'orc' is not a living opponent"
    )
    assert "rejected: target 'orc' is not a living opponent" in prompt


def test_map_decision_builds_attack_proposal() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {"action_type": "attack", "target_id": "gob", "public_message": " I strike! "},
        _perception(),
    )
    assert decision.proposal.actor_id == CharacterId("brix")
    assert decision.proposal.target_id == CharacterId("gob")
    assert decision.proposal.weapon_id is None
    assert decision.public_message == "I strike!"


def test_map_decision_rejects_dead_target() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="not a living opponent"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "attack", "target_id": "orc", "public_message": "hi"},
            _perception(),
        )


def test_map_decision_rejects_unknown_target() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="not a living opponent"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "attack", "target_id": "nobody", "public_message": "hi"},
            _perception(),
        )


def test_map_decision_rejects_unsupported_action_type() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="action_type"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "dodge", "target_id": "gob", "public_message": "hi"},
            _perception(),
        )


def test_map_decision_rejects_empty_public_message() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="public_message"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "attack", "target_id": "gob", "public_message": "   "},
            _perception(),
        )


def test_schema_accepts_a_valid_decision() -> None:
    validate_against_schema(
        {"action_type": "attack", "target_id": "gob", "public_message": "I attack."},
        ATTACK_DECISION_SCHEMA,
    )  # does not raise


def test_schema_rejects_extra_keys_and_other_actions() -> None:
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {"action_type": "attack", "target_id": "gob", "public_message": "x", "extra": 1},
            ATTACK_DECISION_SCHEMA,
        )
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {"action_type": "cast_spell", "target_id": "gob", "public_message": "x"},
            ATTACK_DECISION_SCHEMA,
        )
