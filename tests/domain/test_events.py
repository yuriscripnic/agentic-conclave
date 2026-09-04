from datetime import UTC, datetime

from domain.common.ids import CampaignId, CharacterId, GameId
from domain.events.base import BaseEvent
from domain.events.collector import EventCollector
from domain.events.events import (
    ActionRejected,
    AttackResolved,
    CombatEnded,
    CombatStarted,
    DamageApplied,
    GameCreated,
    GameStarted,
)


def test_event_type_is_derived_snake_case() -> None:
    assert GameStarted().event_type == "game_started"
    assert ActionRejected(
        actor_id=CharacterId.generate(), action_type="attack", reason="no"
    ).event_type == "action_rejected"
    assert CombatEnded(winner_side="party", round_number=3).event_type == "combat_ended"


def test_base_event_is_usable_protocol_implementation() -> None:
    assert issubclass(GameStarted, BaseEvent)


def test_payload_serializes_ids_enums_and_tuples() -> None:
    campaign_id = CampaignId.generate()
    payload = GameCreated(campaign_id=campaign_id, seed=42).to_payload()
    assert payload["campaign_id"] == str(campaign_id)
    assert isinstance(payload["campaign_id"], str)
    assert payload["seed"] == 42

    participant = CharacterId.generate()
    started = CombatStarted(
        participant_ids=(participant,), round_number=1
    ).to_payload()
    assert started["participant_ids"] == [str(participant)]


def test_attack_resolved_payload() -> None:
    attacker = CharacterId.generate()
    target = CharacterId.generate()
    payload = AttackResolved(
        attacker_id=attacker,
        target_id=target,
        roll=15,
        attack_bonus=5,
        total=20,
        target_ac=13,
        hit=True,
        critical=False,
    ).to_payload()
    assert payload == {
        "attacker_id": str(attacker),
        "target_id": str(target),
        "roll": 15,
        "attack_bonus": 5,
        "total": 20,
        "target_ac": 13,
        "hit": True,
        "critical": False,
    }


def test_collector_assigns_contiguous_sequences_and_timestamps() -> None:
    game_id = GameId.generate()
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    collector = EventCollector(game_id=game_id, clock=lambda: fixed)

    first = collector.record(GameStarted())
    second = collector.record(
        DamageApplied(
            character_id=CharacterId.generate(), amount=4, hp_before=7, hp_after=3
        )
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.game_id == game_id
    assert first.occurred_at == "2026-01-01T00:00:00+00:00"
    assert first.event_type == "game_started"
    assert [e.sequence for e in collector.events] == [1, 2]


def test_drain_returns_pending_only_once() -> None:
    collector = EventCollector(game_id=GameId.generate())
    collector.record(GameStarted())

    drained = collector.drain()
    assert [e.event_type for e in drained] == ["game_started"]
    assert collector.drain() == []
    # history is retained for in-process inspection
    assert len(collector.events) == 1


def test_combat_ended_event_payload() -> None:
    payload = CombatEnded(winner_side="party", round_number=2).to_payload()
    assert payload == {"winner_side": "party", "round_number": 2}
