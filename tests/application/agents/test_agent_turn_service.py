"""AgentTurnService decision-loop tests (scripted fake gateway, no real LLM)."""

import pytest

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile, ModelProfileCatalog
from application.agents.agent_turn_service import AgentNotRegisteredError, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway
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


def _goblin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Goblin",
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


def _party_with_brix_first(
    game_service: GameService,
) -> tuple[GameId, CharacterId, CharacterId]:
    """Create Arin + Brix + Goblin and start combat; find a seed where Brix acts first."""
    for seed in range(1, 500):
        game_id = game_service.create_game(CreateGameCommand(seed=seed))
        game_service.add_character(game_id, _fighter("Arin"))
        brix_id = game_service.add_character(game_id, _fighter("Brix"))
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
) -> AgentTurnService:
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=3))
    agent_profiles = AgentProfileCatalog(
        max_action_retries=max_action_retries,
        agents={"brix": _BRIX},
    )
    return AgentTurnService(game_service, runtime, _MODEL_CATALOG, agent_profiles)


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


def test_full_fight_completes_with_the_agent_in_the_party() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)

    def _decision() -> dict[str, str]:
        view = game_service.get_view(game_id)
        target = next(enemy for enemy in view.enemies if not enemy.is_defeated)
        return {"action_type": "attack", "target_id": target.id, "public_message": "I attack."}

    gateway = ScriptedAgentGateway(FakeModelGateway(), _decision)
    service = _agent_service(game_service, gateway)
    service.register(brix_id, _BRIX)

    for _ in range(200):
        view = game_service.get_view(game_id)
        if view.status == "ended":
            break
        active = view.combat.active_actor_id if view.combat else None
        if active is None:
            break
        if active == brix_id.value:
            service.take_turn(game_id, brix_id)
        elif active == goblin_id.value:
            game_service.run_active_enemy_turns(game_id)
        else:
            game_service.submit_action(
                SubmitActionCommand(
                    game_id=game_id,
                    actor_id=CharacterId(active),
                    action_type="attack",
                    target_id=goblin_id,
                )
            )

    assert game_service.get_view(game_id).status == "ended"
