from domain.common.ids import GameId
from domain.events.collector import EventCollector
from domain.events.events import GameStarted
from infrastructure.events.in_memory import InMemoryEventRepository


def test_in_memory_event_repository_roundtrip() -> None:
    repository = InMemoryEventRepository()
    game_id = GameId.generate()
    collector = EventCollector(game_id=game_id)
    first = collector.record(GameStarted())
    second = collector.record(GameStarted())

    repository.append(game_id, first)
    repository.append(game_id, second)

    stored = repository.get_events(game_id)
    assert [e.sequence for e in stored] == [1, 2]
    assert repository.get_events(GameId.generate()) == []
