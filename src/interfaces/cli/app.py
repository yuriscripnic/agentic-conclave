"""CLI adapter — translates input into application commands (CLAUDE.md §42, §63)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable

from rich.console import Console

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.views import GameView
from domain.common.errors import DomainError, PersistenceError
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository
from infrastructure.persistence.postgres.connection import connect
from infrastructure.persistence.postgres.migrate import run_migrations
from infrastructure.persistence.postgres.repository import (
    PostgresEventRepository,
    PostgresGameRepository,
)
from interfaces.cli.renderer import render_game_view, render_report


def parse_input(raw: str) -> tuple[str, str]:
    stripped = raw.strip()
    if not stripped:
        return ("empty", "")
    if stripped.startswith("/"):
        return ("command", stripped)
    parts = stripped.split(None, 1)
    if parts[0].lower() == "attack" and len(parts) == 2:
        return ("attack", parts[1].strip())
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


def _resolve_target(view: GameView, token: str) -> str | None:
    for member in (*view.party, *view.enemies):
        if member.id == token or member.name.lower() == token.lower():
            return member.id
    return None


def _is_enemy(view: GameView, character_id: str) -> bool:
    return any(member.id == character_id for member in view.enemies)


def _arin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Arin",
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


def _goblin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Goblin",
        character_type="enemy",
        level=1,
        strength=8,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=8,
        charisma=8,
        armor_class=13,
        speed_ft=30,
        max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar",
            name="Scimitar",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def main(
    argv: list[str] | None = None,
    console: Console | None = None,
    service: GameService | None = None,
    input_fn: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="conclave")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--db", choices=("memory", "postgres"), default="memory")
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

    game_id = service.create_game(CreateGameCommand(seed=args.seed))
    service.add_character(game_id, _arin())
    service.add_character(game_id, _goblin())
    service.start_combat(game_id)

    while True:
        view = service.get_view(game_id)
        render_game_view(console, view)
        if view.status == "ended":
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
                return 0
            if argument == "/status":
                continue
            if argument == "/help":
                console.print("Commands: attack <target>, /status, /help, /quit")
            else:
                console.print(f"Unknown command: {argument}")
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
            continue
        console.print("Unknown input — try: attack <target>")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
