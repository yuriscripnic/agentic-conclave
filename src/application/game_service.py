"""Coordinates game use cases; rules live in the domain (CLAUDE.md §6)."""

from __future__ import annotations

import secrets

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
)
from application.ports import GameRepository
from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
    TurnReport,
)
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
from domain.common.ids import CampaignId, CharacterId, GameId
from domain.events.collector import EventCollector, EventEnvelope
from domain.events.events import GameCreated, GameStarted
from domain.events.repository import EventRepository
from domain.rules.actions import AttackProposal
from domain.rules.dice import DiceRoller
from domain.world.game import Game, GameStatus

MAX_ENEMY_CHAIN_TURNS = 200

# Command-layer vocabulary -> domain enum (the boundary never leaks domain values).
_CHARACTER_TYPES: dict[str, CharacterType] = {
    "player": CharacterType.PLAYER_CHARACTER,
    "enemy": CharacterType.MONSTER,
    "npc": CharacterType.NPC,
}


class GameService:
    def __init__(
        self, game_repository: GameRepository, event_repository: EventRepository
    ) -> None:
        self._games = game_repository
        self._events = event_repository
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
        for envelope in drained:
            self._events.append(game.game_id, envelope)
        self._games.save(game)
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
        if game.status is not GameStatus.CREATED:
            raise ValidationError("combat can only be started once per game")
        if not game.party_ids or not game.enemy_ids:
            raise ValidationError(
                "combat needs at least one party member and one enemy"
            )
        game.mark_started()
        collector = self._collector(game)
        collector.record(GameStarted())
        engine = self._engine(game)
        combat = engine.start(game, (*game.party_ids, *game.enemy_ids), collector)
        self._combats[game_id] = combat
        self._persist(game)
        return self.get_view(game_id)

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
        if result.valid and combat.status is CombatStatus.ACTIVE:
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
            )
        return GameView(
            game_id=str(game.game_id),
            campaign_name=game.campaign_name,
            status=game.status.value,
            party=[
                self._character_view(game.characters[cid]) for cid in game.party_ids
            ],
            enemies=[
                self._character_view(game.characters[cid]) for cid in game.enemy_ids
            ],
            combat=combat_view,
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
