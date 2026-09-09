"""GmDirector hook tests — cadence, say flow, failure policy (spec D3/D9/D10)."""

from collections.abc import Mapping
from typing import Any

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelRequestError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile, ModelProfileCatalog
from ai.models.types import LLMInvocation, ModelRequest, StructuredModelResponse
from application.commands import AddCharacterCommand, CreateGameCommand, WeaponSpec
from application.game_service import GameService
from application.gm.conversation import GmConversation
from application.gm.director import GmDirector
from application.gm.profiles import GmProfile
from application.telemetry import TelemetrySink
from application.views import TurnReport
from domain.common.ids import EventId, GameId
from domain.events.collector import EventEnvelope
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository

_MODEL_CATALOG = ModelProfileCatalog(
    default_provider="fake",
    profiles={
        "gm": ModelProfile(
            name="gm",
            provider="fake",
            model="test-model",
            temperature=0.8,
            max_tokens=256,
        )
    },
    pricing={},
)

_PROFILE = GmProfile(
    name="DM",
    style="Terse.",
    narration_max_chars=280,
    reply_max_chars=200,
    history_limit=12,
)

_GAME_ID = GameId("00000000-0000-0000-0000-000000000001")


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
        armor_class=13,
        speed_ft=30,
        max_hp=16,
        weapon=WeaponSpec(
            weapon_id="greataxe",
            name="Greataxe",
            damage_die_count=1,
            damage_die_size=12,
        ),
    )


class _RecordingTelemetrySink:
    def __init__(self) -> None:
        self.records: list[LLMInvocation] = []

    def record(self, invocation: LLMInvocation) -> None:
        self.records.append(invocation)


def _director(
    game_service: GameService,
    fake: FakeModelGateway,
    telemetry: TelemetrySink | None = None,
) -> tuple[GmDirector, GmConversation]:
    conversation = GmConversation()
    runtime = AgentRuntime(fake, RetryPolicy(max_attempts=3))
    director = GmDirector(
        game_service, runtime, _MODEL_CATALOG, _PROFILE, conversation, telemetry=telemetry
    )
    return director, conversation


def _envelope(sequence: int, event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        sequence=sequence,
        event_id=EventId.generate(),
        game_id=_GAME_ID,
        occurred_at="2026-09-08T00:00:00+00:00",
        event_type=event_type,
        payload=payload,
    )


def _scene() -> tuple[GameService, GameId]:
    """A real game with one fighter (Arin) and one orc (Orc Brute)."""
    service = _game_service()
    game_id = service.create_game(CreateGameCommand(seed=42))
    service.add_character(game_id, _fighter("Arin"))
    service.add_character(game_id, _orc())
    return service, game_id


def test_on_combat_open_returns_the_opening_narration() -> None:
    service, game_id = _scene()
    fake = _CapturingFake()
    fake.enqueue_structured({"narration": "Two goblins and an orc block the pass."})
    director, _conversation = _director(service, fake)

    result = director.on_combat_open(game_id)

    assert result.narration == "Two goblins and an orc block the pass."
    assert result.npc_reply is None
    assert result.addressed_to is None
    assert len(result.invocations) == 1
    user = fake.requests[0].messages[-1].content
    assert "Task: narrate_open" in user
    assert "- Arin (fighter): 12/12 HP" in user


def test_on_turn_report_without_notable_events_makes_no_call() -> None:
    service, game_id = _scene()
    fake = _CapturingFake()
    director, _conversation = _director(service, fake)
    view = service.get_view(game_id)
    report = TurnReport(
        game_id=str(game_id),
        accepted=True,
        error_code="",
        reason="",
        events=[
            _envelope(
                1,
                "attack_resolved",
                {
                    "attacker_id": view.party[0].id,
                    "target_id": view.enemies[0].id,
                    "roll": 14,
                    "attack_bonus": 5,
                    "total": 15,
                    "target_ac": 13,
                    "hit": True,
                    "critical": False,
                },
            ),
            _envelope(
                2,
                "damage_applied",
                {
                    "character_id": view.enemies[0].id,
                    "amount": 6,
                    "hp_before": 16,
                    "hp_after": 10,
                },
            ),
        ],
        view=view,
        game_over=False,
    )

    assert director.on_turn_report(game_id, report) is None
    assert fake.requests == []


def test_on_turn_report_with_a_critical_hit_narrates() -> None:
    service, game_id = _scene()
    fake = _CapturingFake()
    fake.enqueue_structured({"narration": "Steel bites deep."})
    director, _conversation = _director(service, fake)
    view = service.get_view(game_id)
    report = TurnReport(
        game_id=str(game_id),
        accepted=True,
        error_code="",
        reason="",
        events=[
            _envelope(
                1,
                "attack_resolved",
                {
                    "attacker_id": view.party[0].id,
                    "target_id": view.enemies[0].id,
                    "roll": 20,
                    "attack_bonus": 5,
                    "total": 25,
                    "target_ac": 13,
                    "hit": True,
                    "critical": True,
                },
            ),
        ],
        view=view,
        game_over=False,
    )

    result = director.on_turn_report(game_id, report)

    assert result is not None
    assert result.narration == "Steel bites deep."
    user = fake.requests[0].messages[-1].content
    assert "Task: react_to_events" in user
    assert "Arin landed a CRITICAL hit on Orc Brute (25 vs AC 13)." in user


def test_on_player_say_records_both_sides_and_answers() -> None:
    service, game_id = _scene()
    fake = _CapturingFake()
    fake.enqueue_structured(
        {
            "narration": "The orc grins.",
            "npc_reply": "Fresh meat!",
            "addressed_to": "Orc Brute",
        }
    )
    director, conversation = _director(service, fake)

    result = director.on_player_say(game_id, "Can we  talk this out?")

    assert result.npc_reply == "Fresh meat!"
    assert result.addressed_to == "Orc Brute"
    lines = [(message.speaker, message.text) for message in conversation.recent(10)]
    assert ("player", "Can we talk this out?") in lines
    assert ("Orc Brute", "Fresh meat!") in lines
    user = fake.requests[0].messages[-1].content
    assert "Task: respond_to_player" in user
    assert "- player: Can we talk this out?" in user


def test_model_failure_returns_an_empty_result_with_the_invocation() -> None:
    service, game_id = _scene()
    fake = FakeModelGateway()
    fake.enqueue_error(ModelRequestError("gateway down"))
    director, _conversation = _director(service, fake)

    result = director.on_combat_open(game_id)

    assert result.narration is None
    assert result.npc_reply is None
    assert result.addressed_to is None
    assert len(result.invocations) == 1
    assert result.invocations[0].status == "error"


def test_mapping_failure_returns_an_empty_result() -> None:
    """A whitespace-only narration passes the schema but carries no content."""
    service, game_id = _scene()
    fake = _CapturingFake()
    fake.enqueue_structured({"narration": "   "})
    director, _conversation = _director(service, fake)

    result = director.on_combat_open(game_id)

    assert result.narration is None
    assert result.npc_reply is None
    assert result.addressed_to is None
    assert len(result.invocations) == 1
    assert result.invocations[0].status == "ok"


def test_gm_invocations_are_stamped_with_the_gm_agent_id() -> None:
    service, game_id = _scene()
    fake = _CapturingFake()
    fake.enqueue_structured({"narration": "Two foes block the pass."})
    telemetry = _RecordingTelemetrySink()
    director, _conversation = _director(service, fake, telemetry)

    result = director.on_combat_open(game_id, correlation_id="corr-7")

    assert result.narration is not None
    assert len(telemetry.records) == 1
    invocation = telemetry.records[0]
    assert invocation.agent_id == "gm"
    assert invocation.game_id == str(game_id)
    assert invocation.correlation_id == "corr-7"
    assert invocation.timestamp is not None
    assert result.invocations[0].agent_id == "gm"


def test_failed_gm_calls_are_stamped_too() -> None:
    service, game_id = _scene()
    fake = FakeModelGateway()
    fake.enqueue_error(ModelRequestError("gateway down"))
    telemetry = _RecordingTelemetrySink()
    director, _conversation = _director(service, fake, telemetry)

    result = director.on_combat_open(game_id)

    assert result.narration is None
    assert len(telemetry.records) == 1
    assert telemetry.records[0].agent_id == "gm"
    assert telemetry.records[0].status == "error"
    assert result.invocations[0].agent_id == "gm"
