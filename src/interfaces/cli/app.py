"""CLI adapter — renders sessions from the shared composition root (§42, §63)."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable

from rich.console import Console
from rich.table import Table

from ai.models.errors import ModelError
from application.agents.agent_turn_service import AgentTurnReport
from application.scene.scene_service import SceneTick
from application.views import GameView
from domain.common.errors import DomainError, PersistenceError
from infrastructure.telemetry.in_memory import InMemoryTelemetrySink
from infrastructure.telemetry.logging_sink import configure_telemetry_logging
from interfaces.cli.renderer import render_game_view, render_gm_result, render_report
from session import (
    SessionConfig,
    advance,
    apply_input,
    build_service,
    open_session,
    parse_input,
)

__all__ = ["build_service", "main", "parse_input"]


def _render_agent_turn(console: Console, report: AgentTurnReport, view: GameView) -> None:
    if report.public_message:
        console.print(f"[cyan]{report.actor_name}:[/cyan] {report.public_message}")
    if report.party_message:
        console.print(f"[cyan]{report.actor_name} says:[/cyan] {report.party_message}")
    if report.proposal_source == "fallback" and report.fallback_reason:
        console.print(
            f"[yellow]Fell back to a deterministic attack: {report.fallback_reason}[/yellow]"
        )
    console.print(
        f"[dim]agent {report.actor_id} — source: {report.proposal_source}, "
        f"attempts: {report.action_attempts}, llm calls: {len(report.invocations)}, "
        f"memories: {report.memory_retrieved}[/dim]"
    )
    render_report(console, report.turn_report, view)


def _render_telemetry(console: Console, sink: InMemoryTelemetrySink) -> None:
    """Per-agent/role session totals table (spec §3.6)."""
    totals = sink.snapshot()
    if not totals:
        console.print("[dim]No LLM calls recorded this session.[/dim]")
        return
    table = Table(title="LLM telemetry (this session)")
    for column in (
        "agent", "role", "calls", "retries", "tokens in", "tokens out", "est. cost"
    ):
        table.add_column(column)
    for total in totals:
        table.add_row(
            total.key,
            total.role,
            str(total.calls),
            str(total.retries),
            str(total.input_tokens),
            str(total.output_tokens),
            f"${total.estimated_cost_usd:.6f}",
        )
    console.print(table)


def main(
    argv: list[str] | None = None,
    console: Console | None = None,
    input_fn: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="conclave")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--db", choices=("memory", "postgres"), default="memory")
    parser.add_argument(
        "--agent",
        choices=("off", "llm", "fake"),
        default="off",
        help="add an AI-controlled party member (off | llm | fake)",
    )
    parser.add_argument(
        "--gm",
        choices=("off", "llm", "fake"),
        default="fake",
        help="enable the AI Game Master narrator (off | llm | fake)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="emit per-call LLM telemetry lines (JSON) to stderr or $CONCLAVE_TELEMETRY_LOG",
    )
    parser.add_argument(
        "--world",
        default=None,
        help="location graph TOML (name under config/, e.g. world.toml) for travel scenes",
    )
    # argv=None means "read the process arguments" so the console-script entry
    # point (`conclave = "interfaces.cli.app:main"`) honors its flags; library
    # and test callers pass an explicit list (often []) to stay isolated from
    # the host process's sys.argv.
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    console = console or Console()
    configure_telemetry_logging(debug=args.debug)
    try:
        session = open_session(
            SessionConfig(
                seed=args.seed,
                db=args.db,
                agent_mode=None if args.agent == "off" else args.agent,
                gm_mode=args.gm,
                world_path=args.world,
            )
        )
    except (ValueError, PersistenceError, ModelError) as error:
        console.print(f"[red]{error}[/red]")
        return 2
    if session.party_names:
        console.print(
            f"[cyan]{', '.join(session.party_names)} join the party "
            f"(AI-controlled, mode: {args.agent})[/cyan]"
        )
    if session.opening is not None:
        render_gm_result(
            console,
            session.opening,
            session.game_service.get_view(session.game_id),
        )

    while True:
        view = session.game_service.get_view(session.game_id)
        render_game_view(console, view)
        if view.status == "ended":
            _render_telemetry(console, session.telemetry)
            console.print("The adventure has ended. Thanks for playing!")
            return 0
        try:
            pending = advance(session)
        except DomainError as error:
            console.print(f"[red]{error}[/red]")
            continue
        if pending is not None:
            if pending.kind == "agent":
                assert pending.agent_report is not None  # kind "agent" always carries it
                _render_agent_turn(console, pending.agent_report, view)
            else:
                render_report(console, pending.turn_report, view)
            if pending.gm_result is not None:
                render_gm_result(console, pending.gm_result, view)
            continue

        # Phase 21 scene loop: agents act between human inputs. With
        # tick_seconds == 0 (default) exactly one scene action runs per
        # prompt iteration — the human turn pauses the loop (grill #3).
        if session.scene_service is not None:
            tick = session.scene_service.tick(session.game_id)
            _render_scene_tick(console, tick)
            if session.scene_service.tick_seconds > 0.0:
                time.sleep(min(session.scene_service.tick_seconds, 5.0))
                continue

        try:
            raw = (input_fn or input)("conclave> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0

        outcome = apply_input(session, raw)
        if outcome.kind == "empty":
            continue
        if outcome.kind == "command":
            if outcome.argument == "/quit":
                _render_telemetry(console, session.telemetry)
                return 0
            if outcome.argument == "/status":
                continue
            if outcome.argument == "/telemetry":
                _render_telemetry(console, session.telemetry)
                continue
            if outcome.argument == "/help":
                console.print(
                    "Commands: attack <target>, go <exit>, say <text>,"
                    " /status, /telemetry, /help, /quit"
                )
            else:
                console.print(f"Unknown command: {outcome.argument}")
            continue
        if outcome.kind == "say":
            if outcome.gm_result is None:
                console.print("The GM is off — run with --gm fake or --gm llm to talk.")
            else:
                render_gm_result(console, outcome.gm_result, view)
            continue
        if outcome.kind == "no_target":
            console.print(f"No such character: {outcome.argument}")
            continue
        if outcome.kind == "unknown_exit":
            console.print(f"No exit that way: {outcome.argument}")
            continue
        if outcome.kind == "error":
            console.print(f"[red]{outcome.error}[/red]")
            continue
        if outcome.kind == "travel":
            if outcome.turn_report is not None:
                render_report(console, outcome.turn_report, outcome.turn_report.view)
            if outcome.error is not None:
                console.print(f"[red]{outcome.error}[/red]")
            if outcome.gm_result is not None:
                render_gm_result(console, outcome.gm_result, view)
            continue
        if outcome.kind == "attack":
            if outcome.error is not None:
                console.print(f"[red]{outcome.error}[/red]")
                continue
            if outcome.turn_report is not None:
                render_report(console, outcome.turn_report, view)
            if outcome.gm_result is not None:
                render_gm_result(console, outcome.gm_result, view)
            continue
        console.print("Unknown input — try: attack <target>")


def _render_scene_tick(console: Console, tick: SceneTick) -> None:
    """Render one out-of-combat scene step; never prints internal state."""
    if tick.kind != "scene_action":
        return
    if tick.public_message and tick.actor_name:
        console.print(f"[cyan]{tick.actor_name}[/cyan]: {tick.public_message.strip()}")
    if tick.travel_report is not None:
        render_report(console, tick.travel_report, tick.travel_report.view)
    if tick.narration:
        console.print(f"[italic]{tick.narration}[/italic]")


if __name__ == "__main__":
    raise SystemExit(main())
