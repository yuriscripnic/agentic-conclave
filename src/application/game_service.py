"""Coordinates game use cases; rules live in the domain (CLAUDE.md §6)."""

from __future__ import annotations

import secrets
from collections.abc import Mapping

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    TravelCommand,
)
from application.ports import GameRepository
from application.views import (
    BattleMapView,
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
    SceneView,
    TurnReport,
)
from application.world_catalog import BattleMap
from domain.character.abilities import AbilityScores, AbilityType
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.combat.engine import CombatEngine
from domain.combat.policy import SimpleMeleeEnemyPolicy
from domain.combat.state import Combat, CombatStatus
from domain.common.errors import (
    AgentDecisionFailedError,
    CombatNotActiveError,
    GameNotRunningError,
    InvalidActionError,
    ValidationError,
)
from domain.common.ids import CampaignId, CharacterId, GameId, LocationId
from domain.events.collector import EventCollector, EventEnvelope
from domain.events.events import GameCreated, GameStarted
from domain.events.repository import EventRepository
from domain.rules.actions import AttackProposal
from domain.rules.dice import DiceRoller
from domain.world.game import Game, GameStatus
from domain.world.locations import WorldMap
from domain.world.travel import TravelProposal, TravelService

MAX_ENEMY_CHAIN_TURNS = 200

# Command-layer vocabulary -> domain enum (the boundary never leaks domain values).
_CHARACTER_TYPES: dict[str, CharacterType] = {
    "player": CharacterType.PLAYER_CHARACTER,
    "enemy": CharacterType.MONSTER,
    "npc": CharacterType.NPC,
}


class GameService:
    def __init__(
        self,
        game_repository: GameRepository,
        event_repository: EventRepository,
        *,
        world: WorldMap | None = None,
        battle_map: BattleMap | None = None,
    ) -> None:
        self._games = game_repository
        self._events = event_repository
        self._world = world
        self._battle_map = battle_map
        self._combats: dict[GameId, Combat] = {}
        self._collectors: dict[GameId, EventCollector] = {}
        self._dice: dict[GameId, DiceRoller] = {}

    # -- helpers ---------------------------------------------------------

    def _game(self, game_id: GameId) -> Game:
        return self._games.get(game_id)

    def _collector(self, game: Game) -> EventCollector:
        collector = self._collectors.get(game.game_id)
        if collector is None:
            collector = EventCollector(game_id=game.game_id)
            self._collectors[game.game_id] = collector
        return collector

    def _engine(self, game: Game) -> CombatEngine:
        dice = self._dice.get(game.game_id)
        if dice is None:
            # One seeded roller per game: identical seed + roll order => identical game.
            dice = DiceRoller(seed=game.seed)
            self._dice[game.game_id] = dice
        return CombatEngine(dice)

    def _persist(self, game: Game) -> list[EventEnvelope]:
        drained = self._collector(game).drain()
        self._games.save(game, drained)
        return drained

    # -- use cases ---------------------------------------------------------

    def create_game(self, command: CreateGameCommand) -> GameId:
        game_id = GameId.generate()
        campaign_id = CampaignId.generate()
        seed = command.seed if command.seed is not None else secrets.randbits(32)
        game = Game(
            game_id=game_id,
            campaign_id=campaign_id,
            campaign_name=command.campaign_name,
            seed=seed,
        )
        collector = EventCollector(game_id=game_id)
        self._collectors[game_id] = collector
        collector.record(GameCreated(campaign_id=campaign_id, seed=seed))
        self._persist(game)
        return game_id

    def add_character(
        self, game_id: GameId, command: AddCharacterCommand
    ) -> CharacterId:
        game = self._game(game_id)
        character = self._build_character(command)
        if command.character_type == "enemy":
            game.add_enemy(character)
        else:
            game.add_party_member(character)
        self._persist(game)
        return character.id

    def place_characters(
        self, game_id: GameId, placements: Mapping[CharacterId, LocationId]
    ) -> None:
        """Place characters on the world map and persist.

        Placement is game state: it must go through the service so every
        repository (not just the in-memory one) sees it (CLAUDE.md §2.2, §62).
        """
        game = self._game(game_id)
        for character_id, location_id in placements.items():
            game.place(character_id, location_id)
        self._persist(game)

    def _build_character(self, command: AddCharacterCommand) -> Character:
        character_type = _CHARACTER_TYPES.get(command.character_type)
        if character_type is None:
            raise ValidationError(
                f"unknown character type: {command.character_type}"
            )
        weapon = (
            None
            if command.weapon is None
            else Weapon(
                weapon_id=command.weapon.weapon_id,
                name=command.weapon.name,
                damage_die_count=command.weapon.damage_die_count,
                damage_die_size=command.weapon.damage_die_size,
                ability=AbilityType(command.weapon.ability),
            )
        )
        return Character(
            id=CharacterId.generate(),
            name=command.name,
            character_type=character_type,
            character_class=(
                CharacterClass(command.character_class)
                if command.character_class
                else None
            ),
            level=command.level,
            ability_scores=AbilityScores(
                strength=command.strength,
                dexterity=command.dexterity,
                constitution=command.constitution,
                intelligence=command.intelligence,
                wisdom=command.wisdom,
                charisma=command.charisma,
            ),
            armor_class=command.armor_class,
            speed_ft=command.speed_ft,
            hit_points=HitPoints(current=command.max_hp, maximum=command.max_hp),
            equipped_weapon=weapon,
        )

    def start_combat(self, game_id: GameId) -> GameView:
        game = self._game(game_id)
        if game.status not in (GameStatus.CREATED, GameStatus.RUNNING):
            raise ValidationError(
                "combat can only be started on a created or running game"
            )
        existing = self._combats.get(game_id)
        if existing is not None and existing.status is CombatStatus.ACTIVE:
            raise ValidationError("combat is already active for this game")
        if game.status is GameStatus.CREATED:
            game.mark_started()
        if not game.party_ids or not game.enemy_ids:
            raise ValidationError(
                "combat needs at least one party member and one enemy"
            )
        self._open_combat(game)
        self._persist(game)
        return self.get_view(game_id)

    def _open_combat(self, game: Game) -> None:
        if game.status is GameStatus.CREATED:
            game.mark_started()
        collector = self._collector(game)
        collector.record(GameStarted())
        engine = self._engine(game)
        board = self._battle_map.board if self._battle_map is not None else None
        spawns = self._battle_map.spawns if self._battle_map is not None else None
        combat = engine.start(
            game,
            (*game.party_ids, *game.enemy_ids),
            collector,
            board=board,
            spawns=spawns,
        )
        self._combats[game.game_id] = combat

    def submit_action(self, command: SubmitActionCommand) -> TurnReport:
        game = self._game(command.game_id)
        if game.status is not GameStatus.RUNNING:
            raise GameNotRunningError("the game must be running to submit actions")
        combat = self._combats.get(command.game_id)
        if combat is None:
            raise CombatNotActiveError("no active combat for this game")

        proposal = self._proposal_from(command)
        collector = self._collector(game)
        engine = self._engine(game)

        result = engine.resolve(game, combat, proposal, collector)
        if result.valid:
            # A rejected proposal must not mutate state (CLAUDE.md §28): no turn
            # advance and no enemy chain — the game waits for a legal action.
            if combat.status is CombatStatus.ACTIVE:
                engine.advance_turn(game, combat, collector)
            self._run_enemy_chain(game, combat, engine, collector)

        game_over = combat.status is CombatStatus.ENDED
        if game_over:
            game.mark_ended()
        events = self._persist(game)
        return TurnReport(
            game_id=str(command.game_id),
            accepted=result.valid,
            error_code=result.error_code,
            reason=result.reason,
            events=events,
            view=self.get_view(command.game_id),
            game_over=game_over,
        )

    def _proposal_from(self, command: SubmitActionCommand) -> AttackProposal:
        if command.action_type != "attack":
            raise InvalidActionError(f"unsupported action type: {command.action_type}")
        if command.target_id is None:
            raise InvalidActionError("an attack requires a target")
        return AttackProposal(
            actor_id=command.actor_id,
            target_id=command.target_id,
            weapon_id=command.weapon_id,
        )

    def _run_enemy_chain(
        self,
        game: Game,
        combat: Combat,
        engine: CombatEngine,
        collector: EventCollector,
    ) -> None:
        guard = 0
        while (
            combat.status is CombatStatus.ACTIVE
            and game.side_of(combat.active_actor()) == "enemies"
        ):
            actor_id = combat.active_actor()
            proposal = SimpleMeleeEnemyPolicy().decide(game, actor_id)
            engine.resolve(game, combat, proposal, collector)
            if combat.status is CombatStatus.ACTIVE:
                engine.advance_turn(game, combat, collector)
            guard += 1
            if guard > MAX_ENEMY_CHAIN_TURNS:
                raise AgentDecisionFailedError("enemy turn chain did not terminate")

    def run_active_enemy_turns(self, game_id: GameId) -> TurnReport:
        game = self._game(game_id)
        combat = self._combats.get(game_id)
        if combat is None:
            raise CombatNotActiveError("no active combat for this game")

        collector = self._collector(game)
        engine = self._engine(game)
        if (
            combat.status is CombatStatus.ACTIVE
            and game.side_of(combat.active_actor()) == "enemies"
        ):
            self._run_enemy_chain(game, combat, engine, collector)

        game_over = combat.status is CombatStatus.ENDED
        if game_over:
            game.mark_ended()
        events = self._persist(game)
        return TurnReport(
            game_id=str(game_id),
            accepted=True,
            error_code="",
            reason="",
            events=events,
            view=self.get_view(game_id),
            game_over=game_over,
        )

    def yield_turn(self, game_id: GameId) -> None:
        """End the active actor's turn without an action.

        A rejected proposal does not advance the turn (CLAUDE.md §28 keeps the
        game waiting for a legal action from the human), so the agent fallback
        — whose every attempt the engine rejected — ends the turn itself: with
        static positions an agent left waiting on its own rejected proposals
        would deadlock the fight until R3 movement exists.
        """
        game = self._game(game_id)
        combat = self._combats.get(game_id)
        if combat is None:
            raise CombatNotActiveError("no active combat for this game")
        collector = self._collector(game)
        engine = self._engine(game)
        if combat.status is CombatStatus.ACTIVE:
            engine.advance_turn(game, combat, collector)
            self._run_enemy_chain(game, combat, engine, collector)
        game_over = combat.status is CombatStatus.ENDED
        if game_over:
            game.mark_ended()
        self._persist(game)

    # -- travel / scenes ---------------------------------------------------

    def travel(self, command: TravelCommand) -> TurnReport:
        if self._world is None:
            raise InvalidActionError("this game has no world configured")
        game = self._game(command.game_id)
        if game.status is GameStatus.ENDED:
            raise GameNotRunningError("the game has ended; travel is impossible")
        combat = self._combats.get(command.game_id)
        combat_active = (
            combat is not None and combat.status is CombatStatus.ACTIVE
        )
        outcome = TravelService(self._world).resolve(
            game,
            TravelProposal(actor_id=command.actor_id, direction=command.direction),
            combat_active=combat_active,
            collector=self._collector(game),
        )
        if not outcome.accepted:
            events = self._persist(game)
            return TurnReport(
                game_id=str(command.game_id),
                accepted=False,
                error_code=outcome.reason,
                reason=outcome.reason,
                events=events,
                view=self.get_view(command.game_id),
                game_over=False,
            )
        if outcome.location is None:
            raise InvalidActionError("travel resolved with no destination")
        if self._hostiles_at(game, command.actor_id, outcome.location.id):
            # ONE transaction: arrival + combat opening leave together,
            # and the arrival stays in this report's event list.
            self._open_combat(game)
        events = self._persist(game)
        return TurnReport(
            game_id=str(command.game_id),
            accepted=True,
            error_code="",
            reason="",
            events=events,
            view=self.get_view(command.game_id),
            game_over=False,
        )

    def _hostiles_at(
        self, game: Game, actor_id: CharacterId, location_id: LocationId
    ) -> bool:
        residents = set(game.residents_of(location_id))
        opponents = set(game.opponents_of(actor_id))
        return bool(residents & opponents)

    # -- use cases ---------------------------------------------------------

    def get_view(self, game_id: GameId) -> GameView:
        game = self._game(game_id)
        combat = self._combats.get(game_id)
        combat_view: CombatView | None = None
        if combat is not None:
            active: str | None = None
            if combat.status is CombatStatus.ACTIVE:
                active = str(combat.active_actor())
            combat_view = CombatView(
                round_number=combat.round_number,
                status=combat.status.value,
                active_actor_id=active,
                initiative_order=[
                    InitiativeEntryView(
                        character_id=str(entry.character_id),
                        name=game.characters[entry.character_id].name,
                        total=entry.total,
                    )
                    for entry in combat.entries
                ],
                map=(
                    BattleMapView(
                        width=combat.board.width,
                        height=combat.board.height,
                        walls=tuple(
                            (square.x, square.y)
                            for square in sorted(combat.board.walls)
                        ),
                        positions={
                            str(character_id): (square.x, square.y)
                            for character_id, square in combat.positions.items()
                        },
                    )
                    if combat.board is not None
                    else None
                ),
            )
        return GameView(
            game_id=str(game.game_id),
            campaign_name=game.campaign_name,
            status=game.status.value,
            party=[
                self._character_view(game.characters[cid]) for cid in game.party_ids
            ],
            enemies=self._enemy_views(game, combat),
            combat=combat_view,
            scene=self._scene_view(game),
        )

    def _enemy_views(self, game: Game, combat: Combat | None) -> list[CharacterView]:
        """Enemies visible to the viewer.

        Without a world (or during combat) every enemy is shown; otherwise the
        panel follows the scene, so enemies waiting in another location are not
        presented as present (they cannot be attacked there).
        """
        enemy_ids = list(game.enemy_ids)
        if self._world is not None and combat is None:
            here = self._hero_location(game)
            enemy_ids = [cid for cid in enemy_ids if game.location_of(cid) == here]
        return [self._character_view(game.characters[cid]) for cid in enemy_ids]

    def _hero_location(self, game: Game) -> LocationId | None:
        if self._world is None:
            return None
        hero = (
            game.living_party_ids[0]
            if game.living_party_ids
            else (game.party_ids[0] if game.party_ids else None)
        )
        if hero is None:
            return None
        return game.location_of(hero) or self._world.start_id

    def _scene_view(self, game: Game) -> SceneView | None:
        if self._world is None:
            return None
        here = self._hero_location(game)
        if here is None:
            return None
        location = self._world.get(here)
        return SceneView(
            location_id=str(location.id),
            name=location.name,
            description=location.description,
            exits=[
                (
                    exit_.direction,
                    self._world.get(exit_.destination).name,
                )
                for exit_ in location.exits
            ],
        )

    def _character_view(self, character: Character) -> CharacterView:
        return CharacterView(
            id=str(character.id),
            name=character.name,
            character_class=(
                character.character_class.value if character.character_class else None
            ),
            level=character.level,
            hp_current=character.hit_points.current,
            hp_max=character.hit_points.maximum,
            armor_class=character.armor_class,
            conditions=list(character.conditions),
            is_defeated=character.is_defeated(),
        )

    def get_events(self, game_id: GameId) -> list[EventEnvelope]:
        self._game(game_id)
        return self._events.get_events(game_id)
