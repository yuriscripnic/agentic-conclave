"""AgentTurnService decision-loop tests (scripted fake gateway, no real LLM)."""

from collections.abc import Mapping
from typing import Any

import pytest

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile, ModelProfileCatalog
from ai.models.types import ModelRequest, StructuredModelResponse
from application.agents.agent_turn_service import AgentNotRegisteredError, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway
from application.agents.party_board import PartyMessageBoard
from application.agents.profiles import AgentProfile, AgentProfileCatalog, AgentStats
from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository

_MODEL_CATALOG = ModelProfileCatalog(
    default_provider="fake",
    profiles={
        "player": ModelProfile(
            name="player",
            provider="fake",
            model="test-model",
            temperature=0.1,
            max_tokens=64,
        )
    },
    pricing={},
)
_BRIX_STATS = AgentStats(
    strength=16,
    dexterity=13,
    constitution=15,
    intelligence=10,
    wisdom=12,
    charisma=9,
    armor_class=16,
    speed_ft=30,
    max_hp=12,
    weapon=WeaponSpec(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
    ),
)
_BRIX = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword.",
    objective="Engage the nearest threat.",
    model_profile="player",
    stats=_BRIX_STATS,
)


class _CapturingFake(FakeModelGateway):
    """Records structured-call requests so tests can assert on prompts."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ModelRequest] = []

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self.requests.append(request)
        return await super().generate_structured(request, schema)


def _game_service() -> GameService:
    event_store = InMemoryEventRepository()
    return GameService(InMemoryGameRepository(event_store), event_store)


def _fighter(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword",
            name="Longsword",
            damage_die_count=1,
            damage_die_size=8,
        ),
    )


def _goblin(name: str = "Goblin") -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="enemy",
        level=1,
        strength=8,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=8,
        charisma=8,
        armor_class=13,
        speed_ft=30,
        max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar",
            name="Scimitar",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _rogue(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="rogue",
        level=1,
        strength=10,
        dexterity=16,
        constitution=12,
        intelligence=14,
        wisdom=12,
        charisma=10,
        armor_class=15,
        speed_ft=30,
        max_hp=10,
        weapon=WeaponSpec(
            weapon_id="shortsword",
            name="Shortsword",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _cleric(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="cleric",
        level=1,
        strength=14,
        dexterity=10,
        constitution=14,
        intelligence=9,
        wisdom=16,
        charisma=12,
        armor_class=16,
        speed_ft=30,
        max_hp=11,
        weapon=WeaponSpec(
            weapon_id="mace",
            name="Mace",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _orc() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Orc Brute",
        character_type="enemy",
        level=1,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=7,
        wisdom=10,
        charisma=8,
        armor_class=15,
        speed_ft=30,
        max_hp=15,
        weapon=WeaponSpec(
            weapon_id="greataxe",
            name="Greataxe",
            damage_die_count=1,
            damage_die_size=12,
        ),
    )


def _party_with_brix_first(
    game_service: GameService,
    *extra_party: AddCharacterCommand,
) -> tuple[GameId, CharacterId, CharacterId]:
    """Create Arin + Brix (+ extras) + Goblin, start combat; find a seed where Brix acts first."""
    for seed in range(1, 500):
        game_id = game_service.create_game(CreateGameCommand(seed=seed))
        game_service.add_character(game_id, _fighter("Arin"))
        brix_id = game_service.add_character(game_id, _fighter("Brix"))
        for command in extra_party:
            game_service.add_character(game_id, command)
        goblin_id = game_service.add_character(game_id, _goblin())
        game_service.start_combat(game_id)
        view = game_service.get_view(game_id)
        if view.combat is not None and view.combat.active_actor_id == brix_id.value:
            return game_id, brix_id, goblin_id
    raise AssertionError("no seed in 1..499 lets Brix act first")


def _agent_service(
    game_service: GameService,
    gateway: FakeModelGateway,
    *,
    max_action_retries: int = 2,
    board: PartyMessageBoard | None = None,
) -> AgentTurnService:
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=3))
    agent_profiles = AgentProfileCatalog(
        max_action_retries=max_action_retries,
        agents={"brix": _BRIX},
    )
    return AgentTurnService(
        game_service, runtime, _MODEL_CATALOG, agent_profiles, board=board
    )


def test_model_decision_is_accepted_on_the_first_attempt() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    service = _agent_service(game_service, fake)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    assert report.proposal_source == "model"
    assert report.action_attempts == 1
    assert report.public_message == "I strike."
    assert report.fallback_reason is None
    assert len(report.invocations) == 1
    assert report.turn_report.accepted is True
    assert any(event.event_type == "attack_resolved" for event in report.turn_report.events)


def test_invalid_target_is_fed_back_and_retried() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": "nobody", "public_message": "Who?"}
    )
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "There!"}
    )
    service = _agent_service(game_service, fake)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    assert report.proposal_source == "model"
    assert report.action_attempts == 2
    assert len(report.rejection_reasons) == 1
    assert "not a living opponent" in report.rejection_reasons[0]
    assert len(report.invocations) == 2


def test_transport_exhaustion_falls_back_deterministically() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(6):  # 2 decision attempts x 3 transport attempts
        fake.enqueue_error(ModelTimeoutError("boom"))
    service = _agent_service(game_service, fake, max_action_retries=1)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert report.accepted is True
    assert report.action_attempts == 2
    assert report.fallback_reason is not None
    assert len(report.invocations) == 2  # last invocation of each exhausted runtime call


def test_decision_exhaustion_falls_back_deterministically() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(2):  # max_action_retries=1 -> 2 decision attempts, both invalid
        fake.enqueue_structured(
            {"action_type": "attack", "target_id": "nobody", "public_message": "Who?"}
        )
    service = _agent_service(game_service, fake, max_action_retries=1)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert report.accepted is True
    assert report.turn_report.accepted is True


def test_take_turn_for_unregistered_actor_raises() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    service = _agent_service(game_service, FakeModelGateway())

    with pytest.raises(AgentNotRegisteredError):
        service.take_turn(game_id, brix_id)


def test_accepted_model_turn_posts_the_party_message() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {
            "action_type": "attack",
            "target_id": goblin_id.value,
            "public_message": "I strike.",
            "party_message": "The goblin bleeds — finish it.",
        }
    )
    board = PartyMessageBoard()
    service = _agent_service(game_service, fake, board=board)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.party_message == "The goblin bleeds — finish it."
    assert report.actor_name == "Brix"
    recent = board.recent()
    assert len(recent) == 1
    assert recent[0].actor_name == "Brix"
    assert recent[0].text == "The goblin bleeds — finish it."
    assert recent[0].round_number >= 1


def test_rejected_and_fallback_turns_post_nothing() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(2):  # max_action_retries=1 -> 2 invalid decision attempts, both chatter
        fake.enqueue_structured(
            {
                "action_type": "attack",
                "target_id": "nobody",
                "public_message": "Who?",
                "party_message": "should never be posted",
            }
        )
    board = PartyMessageBoard()
    service = _agent_service(game_service, fake, max_action_retries=1, board=board)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert board.recent() == ()


def _drive_to_actor(
    game_service: GameService,
    service: AgentTurnService,
    game_id: GameId,
    agent_ids: set[str],
    stop_actor_id: str,
    *,
    max_steps: int = 60,
) -> None:
    """Advance enemy/other-agent turns until stop_actor_id is the active actor."""
    for _ in range(max_steps):
        view = game_service.get_view(game_id)
        if view.status == "ended":
            raise AssertionError("combat ended before the target actor's turn")
        active = view.combat.active_actor_id if view.combat else None
        assert active is not None
        if active == stop_actor_id:
            return
        if active in agent_ids:
            service.take_turn(game_id, CharacterId(active))
        else:
            game_service.run_active_enemy_turns(game_id)
    raise AssertionError(f"{stop_actor_id} never became the active actor")


def test_agent_chatter_reaches_the_next_agent_prompt() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service, _rogue("Mira"))
    view = game_service.get_view(game_id)
    assert view.combat is not None
    mira_id = next(member.id for member in view.party if member.name == "Mira")
    mira_profile = AgentProfile(
        name="mira",
        character_name="Mira",
        character_class="rogue",
        persona="Opportunistic.",
        objective="Finish wounded foes.",
        model_profile="player",
        stats=_BRIX_STATS,  # stats are irrelevant to prompts; reuse to keep the test short
    )
    fake = _CapturingFake()

    def _decision() -> dict[str, str]:
        game_view = game_service.get_view(game_id)
        target = next(enemy for enemy in game_view.enemies if not enemy.is_defeated)
        return {
            "action_type": "attack",
            "target_id": target.id,
            "public_message": "I attack.",
            "party_message": "The goblin bleeds — finish it.",
        }

    service = _agent_service(
        game_service, ScriptedAgentGateway(fake, _decision), board=PartyMessageBoard()
    )
    service.register(brix_id, _BRIX)
    service.register(CharacterId(mira_id), mira_profile)

    # Brix acts first by helper contract; her message must reach Mira's prompt.
    _drive_to_actor(game_service, service, game_id, {brix_id.value, mira_id}, mira_id)
    report = service.take_turn(game_id, CharacterId(mira_id))
    assert report.accepted is True

    user_content = fake.requests[-1].messages[-1].content
    assert "Party chatter:" in user_content
    assert "Brix (round" in user_content
    assert "The goblin bleeds — finish it." in user_content


def test_full_four_agent_fight_completes() -> None:
    game_service = _game_service()
    game_id = game_service.create_game(CreateGameCommand(seed=7))
    agent_ids = {
        game_service.add_character(game_id, _fighter("Brix")).value,
        game_service.add_character(game_id, _rogue("Mira")).value,
        game_service.add_character(game_id, _cleric("Sera")).value,
    }
    game_service.add_character(game_id, _fighter("Arin"))
    game_service.add_character(game_id, _goblin("Goblin Scout"))
    game_service.add_character(game_id, _goblin("Goblin Skulker"))
    game_service.add_character(game_id, _orc())
    game_service.start_combat(game_id)

    def _decision() -> dict[str, str]:
        view = game_service.get_view(game_id)
        target = next(enemy for enemy in view.enemies if not enemy.is_defeated)
        return {
            "action_type": "attack",
            "target_id": target.id,
            "public_message": "I attack.",
            "party_message": "Focus the nearest foe.",
        }

    service = _agent_service(
        game_service, ScriptedAgentGateway(FakeModelGateway(), _decision)
    )
    for actor_id in agent_ids:
        service.register(CharacterId(actor_id), _BRIX)

    for _ in range(300):
        view = game_service.get_view(game_id)
        if view.status == "ended":
            break
        active = view.combat.active_actor_id if view.combat else None
        if active is None:
            break
        if active in agent_ids:
            service.take_turn(game_id, CharacterId(active))
        elif any(member.id == active for member in view.enemies):
            game_service.run_active_enemy_turns(game_id)
        else:
            target = next(enemy for enemy in view.enemies if not enemy.is_defeated)
            game_service.submit_action(
                SubmitActionCommand(
                    game_id=game_id,
                    actor_id=CharacterId(active),
                    action_type="attack",
                    target_id=CharacterId(target.id),
                )
            )

    assert game_service.get_view(game_id).status == "ended"
