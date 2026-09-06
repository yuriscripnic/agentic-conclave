# tests/interfaces/test_cli.py
from io import StringIO

import pytest
from rich.console import Console

from interfaces.cli.app import main, parse_input


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


def test_parse_input_variants() -> None:
    assert parse_input("attack goblin") == ("attack", "goblin")
    assert parse_input("  ATTACK Goblin  ") == ("attack", "Goblin")
    assert parse_input("/quit") == ("command", "/quit")
    assert parse_input("   ") == ("empty", "")
    assert parse_input("dance") == ("unknown", "dance")


def test_main_quit_leaves_a_created_game() -> None:
    console, buffer = _console()
    code = main(console=console, input_fn=_scripted("/quit"))
    assert code == 0
    assert "Party" in buffer.getvalue()


def test_main_full_fight_reaches_a_winner() -> None:
    console, buffer = _console()
    lines = (
        ["attack goblin scout"] * 30
        + ["attack goblin skulker"] * 30
        + ["attack orc brute"] * 60
    )
    code = main(console=console, input_fn=_scripted(*lines))
    assert code == 0
    assert "wins the combat" in buffer.getvalue()


def test_build_service_postgres_requires_database_url(monkeypatch) -> None:
    from interfaces.cli.app import build_service

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_service("postgres")


def test_main_reports_missing_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=["--db", "postgres"], console=console, input_fn=_scripted())
    assert code == 2
    assert "DATABASE_URL" in buffer.getvalue()


def test_build_service_rejects_unknown_backend() -> None:
    from interfaces.cli.app import build_service

    with pytest.raises(ValueError, match="unknown database backend"):
        build_service("oracle")


def test_main_agent_fake_plays_a_full_fight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(
        argv=["--agent", "fake"],
        console=console,
        input_fn=_scripted(*(["attack orc brute"] * 60)),
    )
    assert code == 0
    output = buffer.getvalue()
    assert "Brix, Mira, Sera join the party" in output
    assert "AI-controlled" in output
    assert "wins the combat" in output


def test_main_agent_fake_agent_takes_a_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for seed in range(1, 60):
        console, buffer = _console()
        code = main(
            argv=["--agent", "fake", "--seed", str(seed)],
            console=console,
            input_fn=_scripted(*(["attack orc brute"] * 60)),
        )
        assert code == 0
        output = buffer.getvalue()
        if "says:" in output:
            assert "Brix, Mira, Sera join the party" in output
            assert "wins the combat" in output
            assert "AI-controlled" in output
            return
    pytest.fail("no seed in 1..59 gave the agent a turn before the fight ended")


def test_main_agent_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=["--agent", "llm"], console=console, input_fn=_scripted())
    assert code == 2
    assert "OPENROUTER_API_KEY" in buffer.getvalue()


def test_main_agent_off_has_no_agent_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=[], console=console, input_fn=_scripted("/quit"))
    assert code == 0
    assert "AI-controlled" not in buffer.getvalue()


def test_main_all_enemy_names_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(
        console=console,
        input_fn=_scripted(
            "attack goblin scout", "attack goblin skulker", "attack orc brute", "/quit"
        ),
    )
    assert code == 0
    assert "No such character" not in buffer.getvalue()
