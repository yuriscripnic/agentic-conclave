# tests/session/test_factory.py
"""Session composition-root tests (spec §4.1): wiring, opening, postgres."""

from pathlib import Path

import pytest

from session import SessionConfig, apply_input, build_session, open_session


def test_build_session_memory_wires_the_full_fight() -> None:
    session = build_session(SessionConfig(seed=42, agent_mode="fake"))

    assert session.game_id is not None
    assert session.party_names == ("Brix", "Mira", "Sera")
    assert session.turn_service is not None
    assert session.party_board is not None
    view = session.game_service.get_view(session.game_id)
    assert len(view.party) == 4  # Arin + the three agents
    assert [enemy.name for enemy in view.enemies] == [
        "Goblin Scout",
        "Goblin Skulker",
        "Orc Brute",
    ]
    assert view.combat is not None and view.combat.status == "active"


def test_build_session_agent_off_has_an_empty_party() -> None:
    session = build_session(SessionConfig(seed=42))

    assert session.party_names == ()
    assert session.turn_service is None


def test_build_session_gm_off_has_no_director_or_opening() -> None:
    session = open_session(SessionConfig(seed=42, gm_mode="off"))

    assert session.gm_director is None
    assert session.opening is None


def test_open_session_stores_the_opening_narration() -> None:
    session = open_session(SessionConfig(seed=42, agent_mode="fake", gm_mode="fake"))

    assert session.opening is not None
    assert session.opening.narration == (
        "Two goblins and an orc brute block the pass. The fight begins."
    )


def test_build_session_postgres_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_session(SessionConfig(db="postgres"))


def test_build_session_postgres_round_trip(postgres_url, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)

    session = build_session(SessionConfig(seed=42, db="postgres"))

    view = session.game_service.get_view(session.game_id)
    assert view.status == "running"
    assert view.combat is not None


def test_build_session_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown database backend"):
        build_session(SessionConfig(db="oracle"))


def test_agent_llm_requires_opencode_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENCODE_API_KEY"):
        build_session(SessionConfig(seed=42, agent_mode="llm"))


def test_gm_llm_requires_opencode_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENCODE_API_KEY"):
        build_session(SessionConfig(seed=42, gm_mode="llm"))


def test_agent_llm_opencodego_uses_deterministic_embedder(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    session = build_session(SessionConfig(seed=42, agent_mode="llm"))
    turn_service = session.turn_service
    assert turn_service is not None
    memory = turn_service._memory  # composition-root wiring detail; acceptable in tests
    from ai.memory.fake import DeterministicEmbeddingGateway

    assert isinstance(memory._gateway, DeterministicEmbeddingGateway)


def test_agent_llm_openrouter_uses_real_embedding_gateway(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")  # chat key unused in this path
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    session = build_session(
        SessionConfig(seed=42, agent_mode="llm", provider="openrouter")
    )
    turn_service = session.turn_service
    assert turn_service is not None
    memory = turn_service._memory
    from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

    assert isinstance(memory._gateway, OpenRouterModelGateway)

def test_build_session_with_world_places_both_sides_and_does_not_start_combat() -> None:
    session = build_session(SessionConfig(seed=42, world_path=Path("world.toml")))

    view = session.game_service.get_view(session.game_id)
    assert view.scene is not None
    assert view.scene.name == "Ruined Courtyard"
    assert view.combat is None
    assert view.status == "created"
    # enemies wait at the tower, so the courtyard scene shows none
    assert view.enemies == []

    # arriving proves both sides were placed (and opens combat deterministically)
    outcome = apply_input(session, "go north")
    assert outcome.turn_report is not None
    assert [enemy.name for enemy in outcome.turn_report.view.enemies] == [
        "Goblin Scout",
        "Goblin Skulker",
        "Orc Brute",
    ]


def test_postgres_world_session_can_travel(postgres_url, monkeypatch) -> None:
    """Placements are game state: a Postgres reload must not lose them (§21)."""
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    session = build_session(
        SessionConfig(seed=42, db="postgres", world_path=Path("world.toml"))
    )

    outcome = apply_input(session, "go north")

    assert outcome.kind == "travel", outcome.error
