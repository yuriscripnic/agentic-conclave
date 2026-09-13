"""Session composition root: wiring only, no rules, no rendering (spec §4.1).

Extracted from interfaces/cli/app.py with contracts preserved. Lives in a
top-level package because a composition root must import infrastructure, and
the application layer stays infrastructure-free (CLAUDE.md §4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.models.fake import FakeModelGateway
from ai.models.gateway import ModelGateway
from ai.models.profiles import load_model_profiles
from application.agents.agent_turn_service import AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway, ScriptedGmGateway
from application.agents.party_board import PartyMessageBoard
from application.agents.profiles import load_agent_profiles
from application.commands import AddCharacterCommand, CreateGameCommand, WeaponSpec
from application.encounter import load_encounter
from application.game_service import GameService
from application.gm.conversation import GmConversation
from application.gm.director import GmDirector, GmResult
from application.gm.profiles import load_gm_profile
from application.memory.memory_service import MemoryService
from application.telemetry import (
    CompositeTelemetrySink,
    TelemetrySink,
    new_correlation_id,
)
from domain.common.ids import GameId
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
from infrastructure.telemetry.logging_sink import LoggingTelemetrySink
from infrastructure.telemetry.postgres import PostgresTelemetrySink

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class SessionConfig:
    """Everything a caller chooses about a session; wiring stays in the factory."""

    seed: int = 42
    db: str = "memory"  # "memory" | "postgres" (DATABASE_URL from the environment)
    agent_mode: str | None = None  # None ("off") | "fake" | "llm"
    gm_mode: str = "off"  # "off" | "fake" | "llm"
    gateway: ModelGateway | None = None  # overrides the built gateway in every mode
    provider: str | None = None  # provider override for llm modes


@dataclass(frozen=True)
class GameSession:
    """One wired, started game plus the handles a driver needs to run it."""

    game_service: GameService
    game_id: GameId
    telemetry: InMemoryTelemetrySink
    party_board: PartyMessageBoard
    party_names: tuple[str, ...]
    turn_service: AgentTurnService | None
    gm_director: GmDirector | None
    opening: GmResult | None = None


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


PROVIDER_API_KEY_ENV = {
    "opencode-go": "OPENCODE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _resolve_api_key(provider: str, purpose: str) -> str:
    """Map a provider name to its env-var key; fail with the variable's name."""
    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var is None:
        raise ValueError(
            f"unknown provider {provider!r}; known providers: "
            f"{', '.join(sorted(PROVIDER_API_KEY_ENV))}"
        )
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"{env_var} is not set; export it to run with {purpose}")
    return api_key


def _gm_decision(prompt: str) -> dict[str, str]:
    """Deterministic GM responses for fake mode, keyed off the task marker (§3.7)."""
    if "Task: respond_to_player" in prompt:
        return {
            "narration": "The orc shifts its grip on the greataxe and considers you.",
            "npc_reply": "Talk is for the weak. Say your last words!",
            "addressed_to": "Orc Brute",
        }
    if "Task: react_to_events" in prompt:
        return {"narration": "Steel rings through the ravine as another foe falls."}
    return {"narration": "Two goblins and an orc brute block the pass. The fight begins."}


def _fake_or_injected(config: SessionConfig) -> FakeModelGateway:
    """The gateway fake mode wraps: an injected fake, or a fresh one.

    The scripted wrappers re-enqueue decisions on enqueue_structured, which
    only FakeModelGateway provides — a non-fake gateway injected in fake mode
    cannot absorb them, so that is a wiring error, not a silent fallback.
    """
    if isinstance(config.gateway, FakeModelGateway):
        return config.gateway
    if config.gateway is not None:
        raise ValueError(
            "a gateway injected in fake mode must be a FakeModelGateway; "
            "inject a plain ModelGateway only in llm modes"
        )
    return FakeModelGateway()


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


def _wire_gm(
    service: GameService, config: SessionConfig, telemetry: TelemetrySink
) -> GmDirector:
    """Wire the GM director off the shipped gm.toml persona (spec D9)."""
    profile = load_gm_profile(CONFIG_DIR / "gm.toml")
    model_catalog = load_model_profiles(CONFIG_DIR / "llm.toml")
    gateway: ModelGateway
    if config.gm_mode == "llm":
        if config.gateway is not None:
            gateway = config.gateway
        else:
            provider = config.provider or model_catalog.default_provider
            gateway = create_gateway(
                provider, api_key=_resolve_api_key(provider, "--gm llm")
            )
    else:
        gateway = ScriptedGmGateway(_fake_or_injected(config), _gm_decision)
    runtime = AgentRuntime(gateway, RetryPolicy())
    return GmDirector(
        service, runtime, model_catalog, profile, GmConversation(), telemetry=telemetry
    )


def _wire_party(
    service: GameService,
    game_id: GameId,
    config: SessionConfig,
    board: PartyMessageBoard,
    telemetry: TelemetrySink,
) -> tuple[AgentTurnService, tuple[str, ...]]:
    """Wire the agent stack and add the AI party members before combat starts."""
    agent_profiles = load_agent_profiles(CONFIG_DIR / "agents.toml")
    model_catalog = load_model_profiles(CONFIG_DIR / "llm.toml")
    api_key: str | None = None
    if config.agent_mode == "llm":
        if config.gateway is not None:
            gateway = config.gateway
        else:
            provider = config.provider or model_catalog.default_provider
            api_key = _resolve_api_key(provider, "--agent llm")
            gateway = create_gateway(provider, api_key=api_key)
    else:

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

        gateway = ScriptedAgentGateway(_fake_or_injected(config), _decision)
    embedding_profile = model_catalog.get("embedding")
    embedder: EmbeddingGateway
    chat_provider = config.provider or model_catalog.default_provider
    if chat_provider == "opencode-go":
        # OpenCode Go exposes no /embeddings endpoint (spec 2026-09-13,
        # Decision 4): memory embeds with the deterministic gateway.
        embedder = DeterministicEmbeddingGateway()
    elif api_key is not None:
        embedder = create_embedding_gateway(embedding_profile.provider, api_key=api_key)
    else:
        embedder = DeterministicEmbeddingGateway()
    memory = MemoryService(
        embedder,
        _memory_repository(config.db),
        model=embedding_profile.model,
        telemetry=telemetry,
    )
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(
        service,
        runtime,
        model_catalog,
        agent_profiles,
        board=board,
        memory=memory,
        telemetry=telemetry,
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
    # No join line here: rendering belongs to the caller, which reads party_names.
    return agent_service, tuple(names)


def build_session(config: SessionConfig) -> GameSession:
    """Wire a full combat-ready session (spec §4.1); rendering stays with callers."""
    in_memory = InMemoryTelemetrySink()
    sinks: list[TelemetrySink] = [LoggingTelemetrySink(), in_memory]
    if config.db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            sinks.append(PostgresTelemetrySink(connect(database_url)))
    telemetry: TelemetrySink = CompositeTelemetrySink(sinks)

    service = build_service(config.db)
    game_id = service.create_game(CreateGameCommand(seed=config.seed))
    service.add_character(game_id, _fighter("Arin"))

    board = PartyMessageBoard()
    turn_service: AgentTurnService | None = None
    party_names: tuple[str, ...] = ()
    if config.agent_mode is not None:
        turn_service, party_names = _wire_party(
            service, game_id, config, board, telemetry
        )

    gm_director: GmDirector | None = None
    if config.gm_mode != "off":
        gm_director = _wire_gm(service, config, telemetry)

    for enemy_command in load_encounter(CONFIG_DIR / "encounter.toml"):
        service.add_character(game_id, enemy_command)
    service.start_combat(game_id)
    return GameSession(
        game_service=service,
        game_id=game_id,
        telemetry=in_memory,
        party_board=board,
        party_names=party_names,
        turn_service=turn_service,
        gm_director=gm_director,
    )


def open_session(config: SessionConfig) -> GameSession:
    """build_session plus the GM's combat-open narration; ready for input."""
    session = build_session(config)
    if session.gm_director is None:
        return session
    opening = session.gm_director.on_combat_open(
        session.game_id, correlation_id=new_correlation_id()
    )
    return replace(session, opening=opening)