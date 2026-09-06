# tests/integration/test_postgres_wiring.py
"""build_service(db="postgres") wires the real PG repositories end to end (spec §10)."""

from io import StringIO

from rich.console import Console

from application.commands import CreateGameCommand
from infrastructure.persistence.postgres.connection import connect


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=100, force_terminal=False), buffer


def _scripted(*lines: str):
    iterator = iter(lines)

    def _input(prompt: str) -> str:
        try:
            return next(iterator)
        except StopIteration as error:
            raise EOFError from error

    return _input


def test_build_service_postgres_persists_to_real_database(
    postgres_url: str, monkeypatch
) -> None:
    from interfaces.cli.app import build_service

    monkeypatch.setenv("DATABASE_URL", postgres_url)
    service = build_service("postgres")

    game_id = service.create_game(CreateGameCommand(seed=7, campaign_name="Wiring"))

    connection = connect(postgres_url)
    row = connection.execute(
        "SELECT version, status FROM games WHERE id = %s::uuid", (str(game_id),)
    ).fetchone()
    events = connection.execute(
        "SELECT event_type FROM game_events WHERE game_id = %s::uuid ORDER BY sequence",
        (str(game_id),),
    ).fetchall()
    connection.close()

    assert row is not None
    assert row["version"] == 1
    assert row["status"] == "created"
    assert [e["event_type"] for e in events] == ["game_created"]


def test_cli_game_on_postgres_persists_game_and_events(
    postgres_url: str, monkeypatch
) -> None:
    from interfaces.cli.app import main

    # The session database is shared (spec §10): count pre-existing games so the
    # assertions below hold regardless of tests that ran before this one.
    connection = connect(postgres_url)
    games_before = connection.execute(
        "SELECT count(*) AS n FROM games"
    ).fetchone()["n"]
    connection.close()

    monkeypatch.setenv("DATABASE_URL", postgres_url)
    console, buffer = _console()

    code = main(
        argv=["--db", "postgres", "--seed", "42"],
        console=console,
        input_fn=_scripted(
            *(
                ["attack goblin scout"] * 30
                + ["attack goblin skulker"] * 30
                + ["attack orc brute"] * 60
            )
        ),
    )

    assert code == 0
    assert "The adventure has ended" in buffer.getvalue()

    connection = connect(postgres_url)
    games = connection.execute("SELECT status, version FROM games").fetchall()
    event_types = [
        row["event_type"]
        for row in connection.execute(
            "SELECT event_type FROM game_events ORDER BY game_id, sequence"
        ).fetchall()
    ]
    connection.close()

    assert len(games) == games_before + 1
    assert games[-1]["status"] == "ended"
    assert games[-1]["version"] > 1
    assert "attack_resolved" in event_types
    assert "damage_applied" in event_types
    assert "combat_ended" in event_types
