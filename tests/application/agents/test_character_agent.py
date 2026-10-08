"""CharacterAgent prompt and decision-mapping tests."""

from typing import Any

import pytest

from ai.memory.types import MemoryKind, MemoryRecord
from ai.models.errors import ModelInvalidResponseError
from ai.models.schema import validate_against_schema
from application.agents.character_agent import (
    ATTACK_DECISION_SCHEMA,
    CharacterAgent,
    InvalidAgentDecisionError,
)
from application.agents.party_board import PartyMessage
from application.agents.perception import AgentPerception, OpponentBrief
from application.agents.profiles import AgentProfile, AgentStats
from application.commands import WeaponSpec
from application.views import CharacterView
from domain.common.ids import CharacterId

_STATS = AgentStats(
    strength=16,
    dexterity=13,
    constitution=15,
    intelligence=10,
    wisdom=12,
    charisma=9,
    armor_class=16,
    speed_ft=30,
    max_hp=12,
    weapon_id="longsword",
    weapon=WeaponSpec(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
    ),
)

_PROFILE = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword who prefers finishing fights quickly and safely.",
    objective="Survive the skirmish and protect Arin; engage the nearest threat.",
    model_profile="player",
    stats=_STATS,
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


def test_schema_allows_optional_party_message() -> None:
    validate_against_schema(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "x",
            "party_message": "Focus the orc.",
        },
        ATTACK_DECISION_SCHEMA,
    )  # does not raise


def test_schema_rejects_non_string_party_message() -> None:
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {
                "action_type": "attack",
                "target_id": "gob",
                "public_message": "x",
                "party_message": 3,
            },
            ATTACK_DECISION_SCHEMA,
        )


def test_map_decision_missing_or_blank_party_message_is_silence() -> None:
    agent = CharacterAgent(_PROFILE)
    silent = agent.map_decision(
        {"action_type": "attack", "target_id": "gob", "public_message": "hi"},
        _perception(),
    )
    blank = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "party_message": "  ",
        },
        _perception(),
    )
    assert silent.party_message is None
    assert blank.party_message is None


def test_map_decision_non_string_party_message_is_silence() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {"action_type": "attack", "target_id": "gob", "public_message": "hi", "party_message": 7},
        _perception(),
    )
    assert decision.party_message is None


def test_map_decision_collapses_newlines_and_strips() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "party_message": "  Focus\nthe orc!\n",
        },
        _perception(),
    )
    assert decision.party_message == "Focus the orc!"


def test_map_decision_truncates_to_200_chars() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "party_message": "x" * 500,
        },
        _perception(),
    )
    assert decision.party_message is not None
    assert len(decision.party_message) == 200


def test_user_prompt_renders_party_chatter() -> None:
    chatter = (
        PartyMessage(actor_name="Mira", text="The goblin bleeds — finish it.", round_number=1),
        PartyMessage(actor_name="Sera", text="Watch the orc.", round_number=1),
    )
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), party_messages=chatter)
    assert "Party chatter:" in prompt
    assert "- Mira (round 1): The goblin bleeds — finish it." in prompt
    assert "- Sera (round 1): Watch the orc." in prompt
    assert prompt.count("HP") == 1  # chatter never leaks enemy stats


def test_user_prompt_omits_chatter_section_when_empty() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), party_messages=())
    assert "Party chatter:" not in prompt


def test_schema_allows_optional_memory_note() -> None:
    validate_against_schema(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "x",
            "memory_note": "The orc hits hard.",
        },
        ATTACK_DECISION_SCHEMA,
    )  # does not raise


def test_schema_rejects_non_string_memory_note() -> None:
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {
                "action_type": "attack",
                "target_id": "gob",
                "public_message": "x",
                "memory_note": 7,
            },
            ATTACK_DECISION_SCHEMA,
        )


def test_map_decision_memory_note_normalization() -> None:
    agent = CharacterAgent(_PROFILE)
    collapsed = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": "  The orc\nhits hard!  ",
        },
        _perception(),
    )
    truncated = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": "x" * 500,
        },
        _perception(),
    )
    silent = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": "   ",
        },
        _perception(),
    )
    numeric = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": 7,
        },
        _perception(),
    )

    assert collapsed.memory_note == "The orc hits hard!"
    assert truncated.memory_note is not None
    assert len(truncated.memory_note) == 200
    assert silent.memory_note is None
    assert numeric.memory_note is None


def test_user_prompt_renders_memories_section() -> None:
    memories = (
        MemoryRecord(
            memory_id="m1",
            game_id="g",
            agent_key="brix",
            kind=MemoryKind.SEMANTIC,
            text="The orc hits hard — stay at range.",
            round_number=2,
            embedding=(1.0,),
        ),
        MemoryRecord(
            memory_id="m2",
            game_id="g",
            agent_key="brix",
            kind=MemoryKind.EPISODIC,
            text="Round 1: attacked Goblin and missed.",
            round_number=1,
            embedding=(0.5,),
        ),
    )
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), memories=memories)

    assert "Memories:" in prompt
    assert "- [semantic] The orc hits hard — stay at range." in prompt
    assert "- [episodic] Round 1: attacked Goblin and missed." in prompt
    assert prompt.count("HP") == 1  # memories never leak enemy stats
    assert "Turn order" in prompt


def test_user_prompt_omits_the_memories_section_when_empty() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), memories=())

    assert "Memories:" not in prompt
