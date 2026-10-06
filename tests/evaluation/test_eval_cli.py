# tests/evaluation/test_eval_cli.py
"""conclave-eval CLI tests: exit codes, artifacts, fast-fail (spec §4.6)."""

import json
import sys
from io import StringIO

import pytest
from pytest import MonkeyPatch
from rich.console import Console

from evaluation.cli import main


def _console() -> tuple:
    buffer = StringIO()
    return Console(file=buffer, width=120, force_terminal=False), buffer


def test_eval_cli_runs_goblin_skirmish_offline(tmp_path) -> None:
    console, buffer = _console()
    out_dir = tmp_path / "results"

    code = main(
        ["--scenario", "goblin-skirmish", "--out-dir", str(out_dir)], console=console
    )

    assert code == 0
    reports = list(out_dir.glob("goblin-skirmish-*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert all(check["passed"] for check in payload["checks"])
    assert "goblin-skirmish" in buffer.getvalue()


def test_eval_cli_repeat_overrides_scenario_runs(tmp_path) -> None:
    console, _ = _console()
    out_dir = tmp_path / "results"

    code = main(
        ["--scenario", "goblin-skirmish", "--repeat", "1", "--out-dir", str(out_dir)],
        console=console,
    )

    assert code == 0
    report = next(out_dir.glob("goblin-skirmish-*.json"))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 1


def test_eval_cli_unknown_scenario_exits_2(tmp_path) -> None:
    console, buffer = _console()

    code = main(
        ["--scenario", "dragon-hoard", "--out-dir", str(tmp_path)], console=console
    )

    assert code == 2
    assert "unknown scenario" in buffer.getvalue()


def test_eval_cli_openrouter_without_api_key_exits_2(
    monkeypatch: MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    console, buffer = _console()

    code = main(["--provider", "openrouter", "--out-dir", str(tmp_path)], console=console)

    assert code == 2
    assert "OPENROUTER_API_KEY" in buffer.getvalue()


def test_eval_cli_opencodego_without_api_key_exits_2(
    monkeypatch: MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    console, buffer = _console()

    code = main(
        ["--provider", "opencode-go", "--out-dir", str(tmp_path)], console=console
    )

    assert code == 2
    assert "OPENCODE_API_KEY" in buffer.getvalue()


def test_eval_cli_opencodego_provider_choice_is_recognized(
    monkeypatch: MonkeyPatch, tmp_path
) -> None:
    """Unknown-scenario error (exit 2) proves --provider parsed; preflight ran first."""
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    console, buffer = _console()

    code = main(
        [
            "--provider",
            "opencode-go",
            "--scenario",
            "dragon-hoard",
            "--out-dir",
            str(tmp_path),
        ],
        console=console,
    )

    assert code == 2
    assert "unknown scenario" in buffer.getvalue()


def test_eval_cli_defaults_to_sys_argv(monkeypatch: MonkeyPatch) -> None:
    """The console script calls ``main()`` with no argv; flags must still parse."""
    monkeypatch.setattr(sys, "argv", ["conclave-eval", "--not-a-flag"])
    console, _buffer = _console()

    with pytest.raises(SystemExit):
        main(console=console)