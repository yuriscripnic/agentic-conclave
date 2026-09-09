"""CLI adapter — translates input into application commands (CLAUDE.md §42, §63)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.models.errors import ModelError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import load_model_profiles
from application.agents.agent_turn_service import AgentTurnReport, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway, ScriptedGmGateway
from application.agents.profiles import load_agent_profiles
from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.encounter import load_encounter
from application.game_service import GameService
from application.gm.conversation import GmConversation
from application.gm.director import GmDirector
from application.gm.profiles import load_gm_profile
from application.memory.memory_service import MemoryService
from application.telemetry import CompositeTelemetrySink, TelemetrySink, new_correlation_id
from application.views import GameView, TurnReport
from domain.common.errors import DomainError, PersistenceError
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.llm import create_embedding_gateway, create_gateway
from infrastructure.memory.in_memory import InMemoryMemoryRepository
from infrastructure.memory.pgvector_repository import PgvectorMemoryRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository
from infrastructure.persistence.postgres.connection import connect
from infrastructure.persistence.postgres.migrate import run_migrations
from infrastructure.persistence.postgres.repository import (
    PostgresEventRepository,
    PostgresGameRepository,
)
from infrastructure.telemetry.in_memory import InMemoryTelemetrySink
from infrastructure.telemetry.logging_sink import (
    LoggingTelemetrySink,
    configure_telemetry_logging,
)
from infrastructure.telemetry.postgres import PostgresTelemetrySink
from interfaces.cli.renderer import render_game_view, render_gm_result, render_report

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def parse_input(raw: str) -> tuple[str, str]:
    stripped = raw.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        return ("command", stripped)
    parts = stripped.split(None, 1)
    if parts[0].lower() == "attack" and len(parts) == 2:
        return ("attack", parts[1].strip())
    if parts[0].lower() == "say" and len(parts) == 2:
        return ("say", parts[1].strip())
    return ("unknown", stripped)


def build_service(db: str = "memory") -> GameService:
    """Wire the application layer onto a persistence backend (spec §8)."""
    if db == "memory":
        event_store = InMemoryEventRepository()
        return GameService(InMemoryGameRepository(event_store), event_store)
    if db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set; copy .env.example and configure it "
                "to run with --db postgres"
            )
        run_migrations(database_url)
        connection = connect(database_url)
        return GameService(
            PostgresGameRepository(connection),
            PostgresEventRepository(connection),
        )
    raise ValueError(f"unknown database backend: {db!r}")


def _memory_repository(db: str) -> MemoryRepository:
    """Choose the memory backend alongside the game persistence backend (spec §3.6)."""
    if db == "memory":
        return InMemoryMemoryRepository()
    if db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set; copy .env.example and configure it "
                "to run with --db postgres"
            )
        return PgvectorMemoryRepository(connect(database_url))
    raise ValueError(f"unknown database backend: {db!r}")


def _gm_decision(prompt: str) -> dict[str, str]:
    """Deterministic GM responses for --gm fake, keyed off the task marker (§3.7)."""
    if "Task: respond_to_player" in prompt:
        return {
            "narration": "The orc shifts its grip on the greataxe and considers you.",
            "npc_reply": "Talk is for the weak. Say your last words!",
            "addressed_to": "Orc Brute",
        }
    if "Task: react_to_events" in prompt:
        return {"narration": "Steel rings through the ravine as another foe falls."}
    return {"narration": "Two goblins and an orc brute block the pass. The fight begins."}


def _wire_gm(service: GameService, mode: str, telemetry: TelemetrySink) -> GmDirector:
    """Wire the GM director off the shipped gm.toml persona (spec D9)."""
    profile = load_gm_profile(_CONFIG_DIR / "gm.toml")
    model_catalog = load_model_profiles(_CONFIG_DIR / "llm.toml")
    if mode == "llm":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set; export it to run with --gm llm")
        gateway = create_gateway(model_catalog.default_provider, api_key=api_key)
    else:
        gateway = ScriptedGmGateway(FakeModelGateway(), _gm_decision)
    runtime = AgentRuntime(gateway, RetryPolicy())
    return GmDirector(
        service, runtime, model_catalog, profile, GmConversation(), telemetry=telemetry
    )


def _gm_react(
    console: Console,
    gm_service: GmDirector | None,
    report: TurnReport,
    *,
    correlation_id: str | None = None,
) -> None:
    """React to a finished turn report; prints nothing when nothing is notable."""
    if gm_service is None:
        return
    result = gm_service.on_turn_report(
        GameId(report.game_id), report, correlation_id=correlation_id
    )
    if result is not None:
        render_gm_result(console, result, report.view)


def _resolve_target(view: GameView, token: str) -> str | None:
    for member in (*view.party, *view.enemies):
        if member.id == token or member.name.lower() == token.lower():
            return member.id
    return None


def _is_enemy(view: GameView, character_id: str) -> bool:
    return any(member.id == character_id for member in view.enemies)


def _fighter(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword",
            name="Longsword",
            damage_die_count=1,
            damage_die_size=8,
        ),
    )


def _wire_party(
    service: GameService,
    game_id: GameId,
    mode: str,
    console: Console,
    db: str,
    telemetry: TelemetrySink,
) -> AgentTurnService:
    """Wire the agent stack and add the AI party members before combat starts."""
    agent_profiles = load_agent_profiles(_CONFIG_DIR / "agents.toml")
    model_catalog = load_model_profiles(_CONFIG_DIR / "llm.toml")
    api_key: str | None = None
    if mode == "llm":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set; export it to run with --agent llm")
        gateway = create_gateway(model_catalog.default_provider, api_key=api_key)
    else:
        fake = FakeModelGateway()

        def _decision() -> dict[str, str]:
            view = service.get_view(game_id)
            living = [enemy for enemy in view.enemies if not enemy.is_defeated]
            target = living[0] if living else view.enemies[0]
            return {
                "action_type": "attack",
                "target_id": target.id,
                "public_message": "I attack the nearest standing foe.",
                "party_message": "Focus the nearest standing foe.",
                "memory_note": "The orc hits hard; stay at range.",
            }

        gateway = ScriptedAgentGateway(fake, _decision)
    embedding_profile = model_catalog.get("embedding")
    embedder: EmbeddingGateway
    if mode == "llm" and api_key is not None:
        embedder = create_embedding_gateway(embedding_profile.provider, api_key=api_key)
    else:
        embedder = DeterministicEmbeddingGateway()
    memory = MemoryService(
        embedder, _memory_repository(db), model=embedding_profile.model, telemetry=telemetry
    )
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(
        service, runtime, model_catalog, agent_profiles, memory=memory, telemetry=telemetry
    )
    names: list[str] = []
    for profile in agent_profiles.agents.values():
        stats = profile.stats
        character_id = service.add_character(
            game_id,
            AddCharacterCommand(
                name=profile.character_name,
                character_type="player",
                character_class=profile.character_class,
                strength=stats.strength,
                dexterity=stats.dexterity,
                constitution=stats.constitution,
                intelligence=stats.intelligence,
                wisdom=stats.wisdom,
                charisma=stats.charisma,
                armor_class=stats.armor_class,
                speed_ft=stats.speed_ft,
                max_hp=stats.max_hp,
                weapon=stats.weapon,
            ),
        )
        agent_service.register(character_id, profile)
        names.append(profile.character_name)
    console.print(
        f"[cyan]{', '.join(names)} join the party (AI-controlled, mode: {mode})[/cyan]"
    )
    return agent_service


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
    service: GameService | None = None,
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
    # argv=None means "no CLI arguments" so library/test callers are isolated
    # from the host process's sys.argv; the __main__ block passes it explicitly.
    args = parser.parse_args(argv if argv is not None else [])

    console = console or Console()
    if service is None:
        try:
            service = build_service(args.db)
        except (ValueError, PersistenceError) as error:
            console.print(f"[red]{error}[/red]")
            return 2

    configure_telemetry_logging(debug=args.debug)
    session_sink = InMemoryTelemetrySink()
    sinks: list[TelemetrySink] = [LoggingTelemetrySink(), session_sink]
    if args.db == "postgres":
        # build_service hard-fails on a missing DATABASE_URL unless `service`
        # was injected directly (tests); degrade to logging-only in that case.
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            sinks.append(PostgresTelemetrySink(connect(database_url)))
    telemetry: TelemetrySink = CompositeTelemetrySink(sinks)

    game_id = service.create_game(CreateGameCommand(seed=args.seed))
    service.add_character(game_id, _fighter("Arin"))
    agent_service: AgentTurnService | None = None
    if args.agent != "off":
        try:
            agent_service = _wire_party(
                service, game_id, args.agent, console, args.db, telemetry
            )
        except (ValueError, ModelError) as error:
            console.print(f"[red]{error}[/red]")
            return 2
    gm_service: GmDirector | None = None
    if args.gm != "off":
        try:
            gm_service = _wire_gm(service, args.gm, telemetry)
        except (ValueError, ModelError) as error:
            console.print(f"[red]{error}[/red]")
            return 2
    for enemy_command in load_encounter(_CONFIG_DIR / "encounter.toml"):
        service.add_character(game_id, enemy_command)
    service.start_combat(game_id)
    if gm_service is not None:
        render_gm_result(
            console,
            gm_service.on_combat_open(game_id, correlation_id=new_correlation_id()),
            service.get_view(game_id),
        )

    while True:
        view = service.get_view(game_id)
        render_game_view(console, view)
        if view.status == "ended":
            _render_telemetry(console, session_sink)
            console.print("The adventure has ended. Thanks for playing!")
            return 0
        if (
            view.combat is not None
            and view.combat.status == "active"
            and view.combat.active_actor_id is not None
            and _is_enemy(view, view.combat.active_actor_id)
        ):
            report = service.run_active_enemy_turns(game_id)
            render_report(console, report, view)
            _gm_react(console, gm_service, report, correlation_id=new_correlation_id())
            continue

        if (
            agent_service is not None
            and view.combat is not None
            and view.combat.status == "active"
            and view.combat.active_actor_id is not None
            and agent_service.is_agent_controlled(CharacterId(view.combat.active_actor_id))
        ):
            try:
                correlation_id = new_correlation_id()
                agent_report = agent_service.take_turn(
                    GameId(view.game_id),
                    CharacterId(view.combat.active_actor_id),
                    correlation_id=correlation_id,
                )
            except DomainError as error:
                console.print(f"[red]{error}[/red]")
                continue
            _render_agent_turn(console, agent_report, view)
            _gm_react(
                console,
                gm_service,
                agent_report.turn_report,
                correlation_id=correlation_id,
            )
            continue

        try:
            raw = (input_fn or input)("conclave> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0

        kind, argument = parse_input(raw)
        if kind == "empty":
            continue
        if kind == "command":
            if argument == "/quit":
                _render_telemetry(console, session_sink)
                return 0
            if argument == "/status":
                continue
            if argument == "/telemetry":
                _render_telemetry(console, session_sink)
                continue
            if argument == "/help":
                console.print(
                    "Commands: attack <target>, say <text>, /status, /telemetry, /help, /quit"
                )
            else:
                console.print(f"Unknown command: {argument}")
            continue
        if kind == "say":
            if gm_service is None:
                console.print("The GM is off — run with --gm fake or --gm llm to talk.")
                continue
            render_gm_result(
                console,
                gm_service.on_player_say(
                    GameId(view.game_id),
                    argument,
                    correlation_id=new_correlation_id(),
                ),
                view,
            )
            continue
        if kind == "attack":
            target_id = _resolve_target(view, argument)
            if target_id is None:
                console.print(f"No such character: {argument}")
                continue
            actor_id = view.combat.active_actor_id if view.combat else None
            if actor_id is None:
                continue
            try:
                report = service.submit_action(
                    SubmitActionCommand(
                        game_id=GameId(view.game_id),
                        actor_id=CharacterId(actor_id),
                        action_type="attack",
                        target_id=CharacterId(target_id),
                    )
                )
            except DomainError as error:
                console.print(f"[red]{error}[/red]")
                continue
            render_report(console, report, view)
            _gm_react(console, gm_service, report, correlation_id=new_correlation_id())
            continue
        console.print("Unknown input — try: attack <target>")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
