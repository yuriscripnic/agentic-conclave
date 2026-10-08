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
from ai.models.profiles import ModelProfileCatalog, load_model_profiles
from application.agents.agent_turn_service import AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway, ScriptedGmGateway
from application.agents.party_board import PartyMessageBoard
from application.agents.profiles import load_agent_profiles
from application.commands import AddCharacterCommand, CreateGameCommand, WeaponSpec
from application.encounter import encounter_map_name, load_encounter
from application.game_service import GameService
from application.gm.conversation import GmConversation
from application.gm.director import GmDirector, GmResult
from application.gm.profiles import load_gm_profile
from application.memory.memory_service import MemoryService
from application.scene.scene_service import SceneLoopConfig, SceneService
from application.telemetry import (
    CompositeTelemetrySink,
    TelemetrySink,
    new_correlation_id,
)
from application.views import CharacterView, GameView
from application.world_catalog import BattleMap, load_battle_map, load_world_catalog
from domain.common.ids import GameId
from domain.rules.ruleset import Ruleset
from domain.space.geometry import distance_ft
from domain.space.square import Square
from domain.world.locations import WorldMap
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.llm import create_embedding_gateway, create_gateway
from infrastructure.memory.in_memory import InMemoryMemoryRepository
from infrastructure.memory.pgvector_repository import PgvectorMemoryRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository
from infrastructure.rules.loader import TomlRuleset, load_ruleset
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
DATA_RULES_DIR = Path(__file__).resolve().parents[2] / "data" / "rules"
DEFAULT_RULESET_ID = "dnd5e-srd-5.2"


def ruleset_id_from_config(config_dir: Path) -> str:
    """The [ruleset] id from config/game.toml; the SRD 5.2 default when absent."""
    import tomllib

    try:
        document = tomllib.loads(
            (config_dir / "game.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_RULESET_ID
    table = document.get("ruleset")
    if not isinstance(table, dict):
        return DEFAULT_RULESET_ID
    ruleset_id = table.get("id", DEFAULT_RULESET_ID)
    if not isinstance(ruleset_id, str) or not ruleset_id.strip():
        return DEFAULT_RULESET_ID
    return ruleset_id


def load_session_ruleset(config_dir: Path, data_root: Path) -> TomlRuleset:
    """Resolve the configured id against the rules-data root (R2 spec §5)."""
    return load_ruleset(data_root / "rules" / ruleset_id_from_config(config_dir))


@dataclass(frozen=True)
class SessionConfig:
    """Everything a caller chooses about a session; wiring stays in the factory."""

    seed: int = 42
    db: str = "memory"  # "memory" | "postgres" (DATABASE_URL from the environment)
    agent_mode: str | None = None  # None ("off") | "fake" | "llm"
    gm_mode: str = "off"  # "off" | "fake" | "llm"
    world_path: Path | str | None = None  # name under config/ or an absolute path (Phase 21)
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
    scene_service: SceneService | None = None
    opening: GmResult | None = None


def build_service(
    db: str = "memory",
    *,
    world: WorldMap | None = None,
    battle_map: BattleMap | None = None,
    ruleset: Ruleset | None = None,
) -> GameService:
    """Wire the application layer onto a persistence backend (spec §8)."""
    if db == "memory":
        event_store = InMemoryEventRepository()
        return GameService(
            InMemoryGameRepository(event_store),
            event_store,
            world=world,
            battle_map=battle_map,
            ruleset=ruleset,
        )
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
            world=world,
            battle_map=battle_map,
            ruleset=ruleset,
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


def _nearest_enemy(view: GameView, living: list[CharacterView]) -> CharacterView | None:
    """The living enemy closest to the active actor on the battle map, if any.

    The scripted fake decision must stay legal on a gridded encounter (R1):
    with no movement resolver until R3, an attack-only agent can never close
    distance, so it targets the foe it can actually reach (5-10-5 distance).
    """
    combat = view.combat
    if combat is None or combat.map is None or combat.active_actor_id is None:
        return None
    positions = combat.map.positions
    actor_square = positions.get(combat.active_actor_id)
    if actor_square is None:
        return None
    actor = Square(*actor_square)
    reachable = [
        enemy
        for enemy in living
        if (square := positions.get(enemy.id)) is not None
        and distance_ft(actor, Square(*square)) <= 5
    ]
    return reachable[0] if reachable else None


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
) -> tuple[AgentTurnService, tuple[str, ...], AgentRuntime, ModelProfileCatalog]:
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
            target = _nearest_enemy(view, living) or view.enemies[0]
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
    return agent_service, tuple(names), runtime, model_catalog


def build_session(config: SessionConfig) -> GameSession:
    """Wire a full combat-ready session (spec §4.1); rendering stays with callers."""
    in_memory = InMemoryTelemetrySink()
    sinks: list[TelemetrySink] = [LoggingTelemetrySink(), in_memory]
    if config.db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            sinks.append(PostgresTelemetrySink(connect(database_url)))
    telemetry: TelemetrySink = CompositeTelemetrySink(sinks)

    world: WorldMap | None = None
    world_start = (
        config.world_path
        if isinstance(config.world_path, Path)
        else (Path(config.world_path) if config.world_path else None)
    )
    if world_start is not None:
        path = world_start if world_start.is_absolute() else CONFIG_DIR / world_start
        world = load_world_catalog(path)
    map_name = encounter_map_name(CONFIG_DIR / "encounter.toml")
    battle_map = (
        load_battle_map(CONFIG_DIR / "maps" / f"{map_name}.toml") if map_name else None
    )
    service = build_service(
        config.db,
        world=world,
        battle_map=battle_map,
        ruleset=load_session_ruleset(CONFIG_DIR, DATA_RULES_DIR.parent),
    )
    game_id = service.create_game(CreateGameCommand(seed=config.seed))
    service.add_character(game_id, _fighter("Arin"))

    board = PartyMessageBoard()
    turn_service: AgentTurnService | None = None
    party_names: tuple[str, ...] = ()
    agent_runtime: AgentRuntime | None = None
    agent_catalog: ModelProfileCatalog | None = None
    if config.agent_mode is not None:
        turn_service, party_names, agent_runtime, agent_catalog = _wire_party(
            service, game_id, config, board, telemetry
        )

    gm_director: GmDirector | None = None
    if config.gm_mode != "off":
        gm_director = _wire_gm(service, config, telemetry)

    ruleset = load_session_ruleset(CONFIG_DIR, DATA_RULES_DIR.parent)
    for enemy_command in load_encounter(CONFIG_DIR / "encounter.toml", ruleset):
        service.add_character(game_id, enemy_command)
    if world is None:
        service.start_combat(game_id)
    else:
        # Phase 21: place both sides; combat opens deterministically when a
        # party member arrives among enemies (TravelService chain). Placement
        # is persisted through the service, not mutated in place, so non-memory
        # repositories keep it (CLAUDE.md §2.2).
        game = service._game(game_id)
        placements = {cid: world.start_id for cid in game.party_ids}
        if world.enemies_at is not None:
            placements |= {cid: world.enemies_at for cid in game.enemy_ids}
        service.place_characters(game_id, placements)
    scene_service: SceneService | None = None
    if world is not None and turn_service is not None:
        assert agent_runtime is not None and agent_catalog is not None
        scene_service = SceneService(
            service,
            world=world,
            turn_service=turn_service,
            gm_director=gm_director,
            runtime=agent_runtime,
            model_catalog=agent_catalog,
            config=_scene_loop_config(),
        )
    return GameSession(
        game_service=service,
        game_id=game_id,
        telemetry=in_memory,
        party_board=board,
        party_names=party_names,
        turn_service=turn_service,
        gm_director=gm_director,
        scene_service=scene_service,
    )


def _scene_loop_config() -> SceneLoopConfig:
    """Loop pacing from config/game.toml (§48); defaults when absent."""
    path = CONFIG_DIR / "game.toml"
    try:
        import tomllib

        loop = tomllib.loads(path.read_text(encoding="utf-8")).get("loop", {})
    except (OSError, tomllib.TOMLDecodeError):
        loop = {}
    if not isinstance(loop, dict):
        loop = {}
    tick_seconds = loop.get("tick_seconds", 0.0)
    max_actions = loop.get("max_agent_scene_actions", 4)
    return SceneLoopConfig(
        tick_seconds=float(tick_seconds) if isinstance(tick_seconds, (int, float)) else 0.0,
        max_agent_scene_actions=max_actions if isinstance(max_actions, int) else 4,
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