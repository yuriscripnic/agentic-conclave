"""Session registry + idempotency store tests."""
import pytest

from domain.common.errors import GameNotFoundError
from interfaces.api.store import IdempotencyStore, SessionRegistry
from session.factory import SessionConfig


def test_build_creates_started_session() -> None:
    registry = SessionRegistry(agent_mode="fake", gm_mode="fake")

    game_id = registry.build(SessionConfig(seed=7))

    assert game_id in registry
    session = registry.get(game_id)
    assert session.game_service.get_view(session.game_id).combat is not None


def test_get_unknown_game_raises() -> None:
    registry = SessionRegistry(agent_mode="fake", gm_mode="fake")

    with pytest.raises(GameNotFoundError):
        registry.get("nope")


def test_locks_are_per_game() -> None:
    registry = SessionRegistry(agent_mode="fake", gm_mode="fake")
    a = registry.build(SessionConfig(seed=1))
    b = registry.build(SessionConfig(seed=2))

    assert registry.lock_for(a) is not registry.lock_for(b)
    assert registry.lock_for(a) is registry.lock_for(a)


def test_idempotency_store_roundtrip_scoped() -> None:
    store = IdempotencyStore()

    assert store.response_or("k1", "POST /games") is None
    store.remember("k1", "POST /games", {"game_id": "game-1"})
    assert store.response_or("k1", "POST /games") == {"game_id": "game-1"}
    assert store.response_or("k1", "games/game-1/actions") is None


def test_empty_key_is_a_no_op() -> None:
    store = IdempotencyStore()

    assert store.response_or("", "POST /games") is None
    store.remember("", "POST /games", {"x": 1})
    assert store.response_or("", "POST /games") is None
