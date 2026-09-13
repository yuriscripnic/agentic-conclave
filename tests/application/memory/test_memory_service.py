"""MemoryService: episodic derivation, semantic notes, batch embedding, retrieval."""

import asyncio
import dataclasses
import uuid

from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.types import EmbeddingRequest, EmbeddingResponse, MemoryKind, MemoryRecord
from ai.models.types import LLMInvocation
from application.agents.perception import AgentPerception, OpponentBrief, build_perception
from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.memory.memory_service import MemoryService, _episodic_text
from application.views import CharacterView, TurnReport
from domain.common.ids import CharacterId, EventId, GameId
from domain.events.collector import EventEnvelope
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.memory.in_memory import InMemoryMemoryRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


class _CapturingEmbeddingGateway:
    """Deterministic embedder that records every request (test double)."""

    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []
        self._inner = DeterministicEmbeddingGateway()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.requests.append(request)
        return await self._inner.embed(request)


def _seed_record(
    game_id: str, agent_key: str, text: str, kind: MemoryKind, round_number: int
) -> MemoryRecord:
    vector = asyncio.run(
        DeterministicEmbeddingGateway().embed(
            EmbeddingRequest(texts=(text,), model="test-model")
        )
    ).vectors[0]
    return MemoryRecord(
        memory_id=uuid.uuid4().hex,
        game_id=game_id,
        agent_key=agent_key,
        kind=kind,
        text=text,
        round_number=round_number,
        embedding=vector,
    )


def _perception() -> AgentPerception:
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
    return AgentPerception(
        round_number=2,
        active_actor_id="brix",
        self_view=me,
        opponents=(
            OpponentBrief(id="gob", name="Goblin", is_defeated=False),
            OpponentBrief(id="orc", name="Orc", is_defeated=True),
        ),
        initiative_order=("Brix", "Goblin", "Arin"),
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


def _brix_first(
    game_service: GameService,
) -> tuple[GameId, CharacterId, CharacterId]:
    """Create Arin + Brix + Goblin, start combat; find a seed where Brix acts first."""
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


def test_retrieve_on_an_empty_repository_returns_nothing() -> None:
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )

    assert service.retrieve("game-1", _perception()) == ()


def test_retrieve_builds_the_query_from_the_perception() -> None:
    gateway = _CapturingEmbeddingGateway()
    service = MemoryService(gateway, InMemoryMemoryRepository(), model="test-model")

    service.retrieve("game-1", _perception())

    assert len(gateway.requests) == 1
    assert gateway.requests[0].model == "test-model"
    query = gateway.requests[0].texts[0]
    assert "Brix" in query
    assert "fighter" in query
    assert "round 2" in query
    assert "Goblin" in query
    assert "Orc" in query


def test_retrieve_returns_relevant_memories_first() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _seed_record("game-1", "brix", "The Goblin hits hard — stay at range.",
                     MemoryKind.SEMANTIC, 1)
    )
    repo.append(
        _seed_record("game-1", "brix", "Zebra quantum piano fortissimo.",
                     MemoryKind.SEMANTIC, 1)
    )
    service = MemoryService(
        DeterministicEmbeddingGateway(), repo, model="test-model"
    )

    memories = service.retrieve("game-1", _perception())

    assert memories[0].text == "The Goblin hits hard — stay at range."


def test_retrieve_respects_the_retrieval_limit() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _seed_record("game-1", "brix", "Goblin hits hard stay at range",
                     MemoryKind.SEMANTIC, 1)
    )
    repo.append(
        _seed_record("game-1", "brix", "Zebra quantum piano fortissimo",
                     MemoryKind.SEMANTIC, 1)
    )
    service = MemoryService(
        DeterministicEmbeddingGateway(), repo, model="test-model", retrieval_limit=1
    )

    memories = service.retrieve("game-1", _perception())

    assert len(memories) == 1
    assert memories[0].text == "Goblin hits hard stay at range"


def test_record_turn_writes_episodic_memory_from_a_real_turn() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)

    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )
    service.record_turn(str(game_id), perception, turn_report)

    memories = service.retrieve(str(game_id), perception)
    episodic = [record for record in memories if record.kind is MemoryKind.EPISODIC]
    assert len(episodic) == 1
    assert episodic[0].text.startswith("Round 1: attacked Goblin and ")
    assert episodic[0].round_number == 1


def test_record_turn_writes_the_semantic_note_verbatim() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(
        str(game_id), perception, turn_report, note="The goblin bleeds — finish it."
    )

    memories = service.retrieve(str(game_id), perception)
    semantic = [record for record in memories if record.kind is MemoryKind.SEMANTIC]
    assert len(semantic) == 1
    assert semantic[0].text == "The goblin bleeds — finish it."


def test_record_turn_batches_all_texts_into_one_embed_call() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    gateway = _CapturingEmbeddingGateway()
    service = MemoryService(gateway, InMemoryMemoryRepository(), model="test-model")
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(str(game_id), perception, turn_report, note="Watch the Goblin.")

    assert len(gateway.requests) == 1
    assert len(gateway.requests[0].texts) == 2


def test_record_turn_without_an_accepted_attack_writes_nothing() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=CharacterId("nobody"),
        )
    )

    service.record_turn(str(game_id), perception, turn_report, note="should not persist")

    assert turn_report.accepted is False
    assert service.retrieve(str(game_id), perception) == ()


def test_record_turn_dedupes_identical_records() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(str(game_id), perception, turn_report, note="Same note.")
    service.record_turn(str(game_id), perception, turn_report, note="Same note.")

    memories = service.retrieve(str(game_id), perception)
    assert len(memories) == 2  # one episodic + one semantic, no duplicates
    assert len({record.kind for record in memories}) == 2


def test_episodic_derivation_covers_hit_miss_critical_defeat_and_no_attack() -> None:
    """Spec §5: pin every derivation branch deterministically with synthetic events."""
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    def envelope(event_type: str, payload: dict[str, object]) -> EventEnvelope:
        return EventEnvelope(
            sequence=1,
            event_id=EventId.generate(),
            game_id=game_id,
            occurred_at="2026-09-06T00:00:00+00:00",
            event_type=event_type,
            payload=payload,
        )

    def report_with(*events: EventEnvelope) -> TurnReport:
        return dataclasses.replace(turn_report, events=list(events))

    def attack_payload(hit: bool, critical: bool) -> dict[str, object]:
        return {
            "attacker_id": brix_id.value,
            "target_id": goblin_id.value,
            "hit": hit,
            "critical": critical,
        }

    damage = envelope("damage_applied", {"character_id": goblin_id.value, "amount": 5})
    defeat = envelope("character_defeated", {"character_id": goblin_id.value})
    hit = envelope("attack_resolved", attack_payload(True, False))
    critical = envelope("attack_resolved", attack_payload(True, True))
    miss = envelope("attack_resolved", attack_payload(False, False))

    assert _episodic_text(perception, report_with(hit, damage)) == (
        "Round 1: attacked Goblin and dealt 5 damage."
    )
    assert _episodic_text(perception, report_with(critical, damage)) == (
        "Round 1: attacked Goblin and dealt 5 damage (critical)."
    )
    assert _episodic_text(perception, report_with(miss)) == (
        "Round 1: attacked Goblin and missed."
    )
    assert _episodic_text(perception, report_with(miss, defeat)) == (
        "Round 1: attacked Goblin and missed; Goblin fell."
    )
    # Damage without an attack_resolved for this actor derives nothing (Decision 6).
    assert _episodic_text(perception, report_with(damage)) is None
    # Enemy-chain damage (targets a party member) never counts as the actor's damage.
    enemy_hit = envelope("damage_applied", {"character_id": brix_id.value, "amount": 4})
    assert _episodic_text(perception, report_with(hit, damage, enemy_hit)) == (
        "Round 1: attacked Goblin and dealt 5 damage."
    )


class _RecordingTelemetrySink:
    """Telemetry double that keeps every enriched record for assertions."""

    def __init__(self) -> None:
        self.records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self.records.append(invocation)


def test_retrieve_stamps_the_embed_invocation_with_the_retrieval_count() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _seed_record(
            "game-1", "brix", "The Goblin hits hard — stay at range.", MemoryKind.SEMANTIC, 1
        )
    )
    telemetry = _RecordingTelemetrySink()
    service = MemoryService(
        DeterministicEmbeddingGateway(), repo, model="test-model", telemetry=telemetry
    )

    memories = service.retrieve("game-1", _perception(), correlation_id="corr-9")

    assert len(memories) == 1
    assert len(telemetry.records) == 1
    invocation = telemetry.records[0]
    assert invocation.operation == "embed"
    assert invocation.agent_id == "brix"
    assert invocation.game_id == "game-1"
    assert invocation.correlation_id == "corr-9"
    assert invocation.retrieval_count == 1
    assert invocation.timestamp is not None


def test_record_turn_stamps_its_embed_invocation() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    telemetry = _RecordingTelemetrySink()
    service = MemoryService(
        DeterministicEmbeddingGateway(),
        InMemoryMemoryRepository(),
        model="test-model",
        telemetry=telemetry,
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(
        str(game_id),
        perception,
        turn_report,
        note="Watch the Goblin.",
        correlation_id="corr-10",
    )

    assert len(telemetry.records) == 1
    invocation = telemetry.records[0]
    assert invocation.operation == "embed"
    assert invocation.agent_id == brix_id.value
    assert invocation.game_id == str(game_id)
    assert invocation.correlation_id == "corr-10"
    assert invocation.retrieval_count == 0
    assert invocation.timestamp is not None


def test_location_scoped_retrieval_filters_episodic_keeps_semantic() -> None:
    here = AgentPerception(
        round_number=1,
        active_actor_id="",
        self_view=CharacterView(
            id="brix", name="Brix", character_class="fighter", level=1,
            hp_current=10, hp_max=10, armor_class=14, conditions=[], is_defeated=False,
        ),
        opponents=(),
        initiative_order=(),
        location="loc-a",
    )
    repository = InMemoryMemoryRepository()
    gateway = _CapturingEmbeddingGateway()
    service = MemoryService(gateway, repository, model="embed-fake")
    vector = asyncio.run(
        gateway._inner.embed(
            EmbeddingRequest(texts=("scene gossip",), model="embed-fake")
        )
    ).vectors[0]
    record_scene = MemoryRecord(
        memory_id="m1", game_id="g1", agent_key="brix",
        kind=MemoryKind.EPISODIC, text="scene gossip",
        round_number=1, embedding=vector, location="loc-a",
    )
    record_elsewhere = MemoryRecord(
        memory_id="m2", game_id="g1", agent_key="brix",
        kind=MemoryKind.EPISODIC, text="elsewhere gossip",
        round_number=2, embedding=vector, location="loc-b",
    )
    record_semantic = MemoryRecord(
        memory_id="m3", game_id="g1", agent_key="brix",
        kind=MemoryKind.SEMANTIC, text="the well is dry",
        round_number=2, embedding=vector, location=None,
    )
    for record in (record_scene, record_elsewhere, record_semantic):
        repository.append(record)

    memories = service.retrieve("g1", here)

    texts = [memory.text for memory in memories]
    assert "elsewhere gossip" not in texts
    assert set(texts) == {"scene gossip", "the well is dry"}
    query_line = gateway.requests[-1].texts[0]
    assert "loc-a" in query_line
