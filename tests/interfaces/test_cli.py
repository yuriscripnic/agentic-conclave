# tests/interfaces/test_cli.py
from io import StringIO

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
    code = main(console=console, input_fn=_scripted(*(["attack goblin"] * 60)))
    assert code == 0
    assert "wins the combat" in buffer.getvalue()
