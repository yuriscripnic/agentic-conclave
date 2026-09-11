# tests/session/test_factory.py
"""Session composition-root tests (spec §4.1): wiring, opening, postgres."""

import pytest

from session import SessionConfig, build_session, open_session


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