# tests/interfaces/test_cli.py
import json
import sys
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
    code = main(argv=[], console=console, input_fn=_scripted("/quit"))
    assert code == 0
    assert "Party" in buffer.getvalue()


def test_main_full_fight_reaches_a_winner() -> None:
    console, buffer = _console()
    lines = (
        ["attack goblin scout"] * 30
        + ["attack goblin skulker"] * 30
        + ["attack orc brute"] * 60
    )
    code = main(argv=[], console=console, input_fn=_scripted(*lines))
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
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=["--agent", "llm"], console=console, input_fn=_scripted())
    assert code == 2
    assert "OPENCODE_API_KEY" in buffer.getvalue()


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
        argv=[],
        console=console,
        input_fn=_scripted(
            "attack goblin scout", "attack goblin skulker", "attack orc brute", "/quit"
        ),
    )
    assert code == 0
    assert "No such character" not in buffer.getvalue()


def test_parse_input_say_verb() -> None:
    assert parse_input("say hello there") == ("say", "hello there")
    assert parse_input("  SAY  hello  ") == ("say", "hello")
    assert parse_input("say") == ("unknown", "say")


def test_main_gm_fake_shows_opening_narration_and_npc_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    # --agent defaults to off: the human fights, so player prompts are
    # deterministic every round. Line plan mirrors test_main_full_fight
    # (a proven seed-42 victory), with one `say` in front.
    lines = (
        ["say what do you want from us?"]
        + ["attack goblin scout"] * 30
        + ["attack goblin skulker"] * 30
        + ["attack orc brute"] * 60
    )
    code = main(argv=["--gm", "fake"], console=console, input_fn=_scripted(*lines))
    assert code == 0
    output = buffer.getvalue()
    assert "The fight begins" in output
    assert "Talk is for the weak" in output
    assert "Orc Brute:" in output


def test_main_gm_off_prints_no_gm_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    lines = (
        ["say what do you want from us?"]
        + ["attack goblin scout"] * 30
        + ["attack goblin skulker"] * 30
        + ["attack orc brute"] * 60
    )
    code = main(argv=["--gm", "off"], console=console, input_fn=_scripted(*lines))
    assert code == 0
    output = buffer.getvalue()
    assert "The fight begins" not in output
    assert "Talk is for the weak" not in output


def test_main_gm_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    console, buffer = _console()
    code = main(argv=["--gm", "llm"], console=console, input_fn=_scripted("/quit"))
    assert code == 2
    assert "OPENCODE_API_KEY" in buffer.getvalue()


def test_main_telemetry_command_prints_session_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(
        argv=["--gm", "fake"],
        console=console,
        input_fn=_scripted("/telemetry", "/quit"),
    )
    assert code == 0
    output = buffer.getvalue()
    # once for /telemetry, once for the /quit session summary
    assert output.count("LLM telemetry") == 2
    assert "calls" in output and "retries" in output


def test_main_end_of_session_summary_precedes_thanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    lines = (
        ["attack goblin scout"] * 30
        + ["attack goblin skulker"] * 30
        + ["attack orc brute"] * 60
    )
    code = main(argv=["--gm", "fake"], console=console, input_fn=_scripted(*lines))
    assert code == 0
    output = buffer.getvalue()
    assert output.index("LLM telemetry") < output.index("Thanks for playing!")


def test_main_debug_emits_parseable_telemetry_lines(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    log_file = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("CONCLAVE_TELEMETRY_LOG", str(log_file))
    console, buffer = _console()

    code = main(
        argv=["--gm", "fake", "--debug"],
        console=console,
        input_fn=_scripted("/quit"),
    )

    assert code == 0
    lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line]
    assert lines  # the GM's opening call is already on the wire
    expected_keys = {
        "ts", "event", "game_id", "agent_id", "correlation_id", "request_id",
        "provider", "model", "operation", "status", "error_kind", "latency_ms",
        "input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd",
        "attempt", "retrieval_count", "tools_called",
    }
    for line in lines:
        payload = json.loads(line)
        assert set(payload) == expected_keys
        assert payload["event"] == "llm_invocation"
        assert payload["agent_id"] == "gm"


def test_main_without_debug_stays_silent(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    log_file = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("CONCLAVE_TELEMETRY_LOG", str(log_file))
    console, buffer = _console()

    code = main(argv=["--gm", "fake"], console=console, input_fn=_scripted("/quit"))

    assert code == 0
    assert log_file.read_text(encoding="utf-8") == ""


def test_main_defaults_to_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console script calls ``main()`` with no argv; flags must still parse."""
    monkeypatch.setattr(sys, "argv", ["conclave", "--definitely-not-a-flag"])
    console, _buffer = _console()

    with pytest.raises(SystemExit):
        main(console=console, input_fn=_scripted())


def test_main_explicit_argv_ignores_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit argv still wins, so library/test callers stay isolated."""
    monkeypatch.setattr(sys, "argv", ["conclave", "--definitely-not-a-flag"])
    console, _buffer = _console()

    assert main(argv=[], console=console, input_fn=_scripted("/quit")) == 0
