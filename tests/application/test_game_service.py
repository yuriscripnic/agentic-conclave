# tests/application/test_game_service.py
import pytest

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.world_catalog import BattleMap
from domain.common.errors import (
    CombatNotActiveError,
    GameNotFoundError,
    GameNotRunningError,
    InvalidActionError,
    ValidationError,
)
from domain.common.ids import CharacterId, GameId
from domain.rules.dice import DiceRoller
from domain.space.board import Board, Spawns
from domain.space.square import Square
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


def _service() -> GameService:
    event_store = InMemoryEventRepository()
    return GameService(InMemoryGameRepository(event_store), event_store)


def _fighter_command(name: str = "Arin", range_ft: int = 5) -> AddCharacterCommand:
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
            range_ft=range_ft,
        ),
    )


def _goblin_command(name: str = "Goblin", range_ft: int = 5) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
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
            range_ft=range_ft,
        ),
    )


def _started_game(
    seed: int = 42,
) -> tuple[GameService, GameId, CharacterId, CharacterId]:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=seed, campaign_name="Ruins"))
    arin_id = service.add_character(game_id, _fighter_command())
    goblin_id = service.add_character(game_id, _goblin_command())
    service.start_combat(game_id)
    return service, game_id, arin_id, goblin_id


def _seed_with_rolls(rolls: list[int]) -> int:
    for seed in range(100_000):
        roller = DiceRoller(seed=seed)
        if [roller.roll_d20().natural for _ in rolls] == rolls:
            return seed
    raise AssertionError("no seed produced the requested rolls")


def test_create_game_emits_game_created_and_persists() -> None:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=42, campaign_name="Ruins"))

    view = service.get_view(game_id)
    assert view.status == "created"
    assert view.campaign_name == "Ruins"
    assert view.combat is None
    assert view.party == []

    events = service.get_events(game_id)
    assert [e.event_type for e in events] == ["game_created"]
    assert events[0].payload["seed"] == 42


def test_get_view_raises_for_unknown_game() -> None:
    service = _service()
    with pytest.raises(GameNotFoundError):
        service.get_view(GameId.generate())


def test_start_combat_emits_expected_events_and_view() -> None:
    service, game_id, arin_id, goblin_id = _started_game()

    view = service.get_view(game_id)
    assert view.status == "running"
    assert [c.id for c in view.party] == [str(arin_id)]
    assert [c.id for c in view.enemies] == [str(goblin_id)]
    assert view.combat is not None
    assert view.combat.status == "active"
    assert view.combat.round_number == 1
    assert view.combat.active_actor_id in {str(arin_id), str(goblin_id)}
    assert len(view.combat.initiative_order) == 2

    types = [e.event_type for e in service.get_events(game_id)]
    assert types[0] == "game_created"
    assert "game_started" in types
    assert types.count("initiative_rolled") == 2
    assert "combat_started" in types
    assert types[-1] == "turn_started"


def test_add_character_rejected_after_combat_starts() -> None:
    service, game_id, _, _ = _started_game()
    with pytest.raises(ValidationError):
        service.add_character(game_id, _fighter_command("Late"))


def test_submit_action_rejects_wrong_turn_without_side_effects() -> None:
    service, game_id, arin_id, goblin_id = _started_game()
    view = service.get_view(game_id)
    assert view.combat is not None
    active = view.combat.active_actor_id
    assert active is not None
    actor_id = goblin_id if active == str(arin_id) else arin_id
    target_id = arin_id if actor_id is goblin_id else goblin_id

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=actor_id,
            action_type="attack",
            target_id=target_id,
        )
    )

    assert report.accepted is False
    assert report.error_code == "not_your_turn"
    assert any(e.event_type == "action_rejected" for e in report.events)
    assert report.view.combat is not None
    assert report.view.combat.active_actor_id == active  # turn did not advance


def test_submit_unknown_action_type_raises() -> None:
    service, game_id, arin_id, _ = _started_game()
    with pytest.raises(InvalidActionError):
        service.submit_action(
            SubmitActionCommand(
                game_id=game_id, actor_id=arin_id, action_type="teleport"
            )
        )


def test_submit_action_requires_a_running_game() -> None:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=1))
    arin_id = service.add_character(game_id, _fighter_command())
    goblin_id = service.add_character(game_id, _goblin_command())
    with pytest.raises(GameNotRunningError):
        service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=arin_id,
                action_type="attack",
                target_id=goblin_id,
            )
        )


def test_run_enemy_turns_requires_active_combat() -> None:
    service = _service()
    game_id = service.create_game(CreateGameCommand(seed=1))
    with pytest.raises(CombatNotActiveError):
        service.run_active_enemy_turns(game_id)


def test_submit_action_runs_enemy_chain_and_stops_at_party() -> None:
    # Rolls: initiative 10 and 10 (goblin wins the DEX tiebreak), then a hit.
    seed = _seed_with_rolls([10, 10, 15])
    service, game_id, arin_id, goblin_id = _started_game(seed=seed)
    view = service.get_view(game_id)
    assert view.combat is not None
    assert view.combat.active_actor_id == str(goblin_id)

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=goblin_id,
            action_type="attack",
            target_id=arin_id,
        )
    )

    assert report.accepted is True
    assert report.game_over is False
    types = [e.event_type for e in report.events]
    assert "attack_requested" in types
    assert "attack_resolved" in types
    assert "damage_applied" in types
    assert types.count("turn_ended") == 1
    assert types[-1] == "turn_started"
    assert report.view.combat is not None
    assert report.view.combat.active_actor_id == str(arin_id)


def test_get_view_projects_the_battle_map() -> None:
    event_store = InMemoryEventRepository()
    battle_map = BattleMap(
        board=Board(
            width=10,
            height=10,
            # This pair iterates (9, 0) then (0, 9) out of the frozenset, so the
            # sorted assertion below actually pins the projection's sort.
            walls=frozenset({Square(0, 9), Square(9, 0)}),
        ),
        spawns=Spawns(party=(Square(0, 0),), enemies=(Square(4, 0),)),
    )
    service = GameService(
        InMemoryGameRepository(event_store), event_store, battle_map=battle_map
    )
    game_id = service.create_game(CreateGameCommand(seed=1))
    arin_id = service.add_character(game_id, _fighter_command())
    goblin_id = service.add_character(game_id, _goblin_command())

    view = service.start_combat(game_id)

    assert view.combat is not None
    board_view = view.combat.map
    assert board_view is not None
    assert board_view.width == 10
    assert board_view.height == 10
    assert board_view.walls == ((0, 9), (9, 0)), "walls must be sorted"
    assert board_view.positions == {
        str(arin_id): (0, 0),
        str(goblin_id): (4, 0),
    }


def test_get_view_omits_the_map_without_a_board() -> None:
    event_store = InMemoryEventRepository()
    service = GameService(InMemoryGameRepository(event_store), event_store)
    game_id = service.create_game(CreateGameCommand(seed=1))
    service.add_character(game_id, _fighter_command())
    service.add_character(game_id, _goblin_command())

    view = service.start_combat(game_id)

    assert view.combat is not None
    assert view.combat.map is None


def _battle_map() -> BattleMap:
    return BattleMap(
        board=Board(width=10, height=10),
        spawns=Spawns(party=(Square(0, 0),), enemies=(Square(4, 0),)),
    )


def test_start_combat_places_combatants_on_the_encounter_map() -> None:
    event_store = InMemoryEventRepository()
    service = GameService(
        InMemoryGameRepository(event_store), event_store, battle_map=_battle_map()
    )
    game_id = service.create_game(CreateGameCommand(seed=1))
    service.add_character(game_id, _fighter_command())
    service.add_character(game_id, _goblin_command())

    view = service.start_combat(game_id)

    assert view.combat is not None
    assert view.combat.map is not None
    assert view.combat.map.positions, "combatants must start on spawn squares"


class _FiveFiveRuleset:
    """A Ruleset stub carrying only the diagonal rule the engine reads."""

    ruleset_id = "test-5_5_5"
    diagonal_rule = "5_5_5"

    def weapon(self, weapon_id: str) -> object:
        raise AssertionError("not used in this test")

    def statblock(self, statblock_id: str) -> object:
        raise AssertionError("not used in this test")

    def character_class(self, class_id: str) -> object:
        raise AssertionError("not used in this test")


def _diagonal_service(*, ruleset: object) -> tuple[GameService, GameId]:
    event_store = InMemoryEventRepository()
    battle_map = BattleMap(
        board=Board(width=10, height=10),
        spawns=Spawns(party=(Square(0, 0),), enemies=(Square(2, 2),)),
    )
    service = GameService(
        InMemoryGameRepository(event_store),
        event_store,
        battle_map=battle_map,
        ruleset=ruleset,  # type: ignore[arg-type]
    )
    game_id = service.create_game(CreateGameCommand(seed=1))
    service.add_character(game_id, _fighter_command(range_ft=10))
    service.add_character(game_id, _goblin_command(range_ft=10))
    return service, game_id


def test_the_default_diagonal_rule_rejects_two_diagonal_steps() -> None:
    service, game_id = _diagonal_service(ruleset=None)
    view = service.start_combat(game_id)
    assert view.combat is not None
    actor_id = CharacterId(str(view.combat.active_actor_id))
    view = service.get_view(game_id)
    side = view.party if str(actor_id) in {m.id for m in view.party} else view.enemies
    foes = view.enemies if side is view.party else view.party
    target_id = CharacterId(foes[0].id)

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=actor_id,
            action_type="attack",
            target_id=target_id,
        )
    )

    assert report.accepted is False
    assert any(e.event_type == "action_rejected" for e in report.events)


def test_the_rulesets_diagonal_rule_reaches_grid_combat() -> None:
    service, game_id = _diagonal_service(ruleset=_FiveFiveRuleset())
    view = service.start_combat(game_id)
    assert view.combat is not None
    actor_id = CharacterId(str(view.combat.active_actor_id))
    view = service.get_view(game_id)
    side = view.party if str(actor_id) in {m.id for m in view.party} else view.enemies
    foes = view.enemies if side is view.party else view.party
    target_id = CharacterId(foes[0].id)

    report = service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=actor_id,
            action_type="attack",
            target_id=target_id,
        )
    )

    assert report.accepted is True
    assert any(e.event_type == "attack_resolved" for e in report.events)
