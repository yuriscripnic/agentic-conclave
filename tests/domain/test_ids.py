from domain.common.ids import (
    AgentId,
    CampaignId,
    CharacterId,
    EntityId,
    EventId,
    GameId,
    LocationId,
    QuestId,
)


def test_entity_id_accepts_non_empty_value() -> None:
    entity_id = EntityId("game-1")
    assert entity_id.value == "game-1"
    assert str(entity_id) == "game-1"


def test_entity_id_rejects_empty_value() -> None:
    import pytest

    with pytest.raises(ValueError):
        EntityId("   ")


def test_generate_returns_distinct_ids_per_type() -> None:
    first = GameId.generate()
    second = GameId.generate()
    assert first != second
    assert isinstance(first, GameId)
    assert isinstance(CharacterId.generate(), CharacterId)


def test_each_id_type_is_distinct_class() -> None:
    for cls in (CampaignId, GameId, CharacterId, AgentId, LocationId, QuestId, EventId):
        assert issubclass(cls, EntityId)
        assert cls.generate().value != ""
