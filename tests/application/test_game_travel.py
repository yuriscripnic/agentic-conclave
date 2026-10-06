"""GameService.travel: validated travel, arrival-driven combat, scene view."""

from pathlib import Path

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    TravelCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.world_catalog import load_world_catalog
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository

WORLD_DOC = """
[world]
start = "courtyard"
enemies_at = "eastern_tower"

[[locations]]
id = "courtyard"
name = "Ruined Courtyard"
description = "Broken flagstones."

[[locations.exits]]
direction = "north"
to = "eastern_tower"

[[locations]]
id = "eastern_tower"
name = "Eastern Tower"
description = "A tower."
"""


def _fighter_command(name: str = "Arin") -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=13, dexterity=10, constitution=10,
        intelligence=10, wisdom=10, charisma=10,
        armor_class=14,
        speed_ft=30,
        max_hp=50,
        weapon=WeaponSpec(
            weapon_id="longsword", name="Longsword",
            damage_die_count=1, damage_die_size=8,
        ),
    )


def _goblin_command(name: str = "Goblin Scout") -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="enemy",
        level=1,
        strength=10, dexterity=13, constitution=10,
        intelligence=10, wisdom=10, charisma=10,
        armor_class=13,
        speed_ft=30,
        max_hp=70,
        weapon=None,
    )


class _Fixture:
    def __init__(self, tmp_path: Path):
        self.world_path = tmp_path / "world.toml"
        self.world_path.write_text(WORLD_DOC)
        self.world = load_world_catalog(self.world_path)
        self.service = GameService(
            InMemoryGameRepository(InMemoryEventRepository()),
            InMemoryEventRepository(),
            world=self.world,
        )
        self.game_id = self.service.create_game(
            CreateGameCommand(seed=42, campaign_name="Ruins")
        )
        self.hero = self.service.add_character(
            self.game_id, _fighter_command()
        )
        self.goblin = self.service.add_character(
            self.game_id, _goblin_command()
        )
        tower = next(
            exit.destination for exit in self.world.get(self.world.start_id).exits
        )
        # party starts at the courtyard, enemy lurks in the tower
        game = self.service._game(self.game_id)
        game.place(self.hero, self.world.start_id)
        game.place(self.goblin, tower)


def test_travel_moves_party_member_and_recorded(tmp_path) -> None:
    fx = _Fixture(tmp_path)
    report = fx.service.travel(
        TravelCommand(game_id=fx.game_id, actor_id=fx.hero, direction="north")
    )
    assert report.accepted
    assert report.view.scene is not None
    assert report.view.scene.name == "Eastern Tower"
    assert "character_arrived" in [e.event_type for e in report.events]


def test_travel_combat_opened_on_hostile_arrival(tmp_path) -> None:
    fx = _Fixture(tmp_path)
    report = fx.service.travel(
        TravelCommand(game_id=fx.game_id, actor_id=fx.hero, direction="north")
    )
    assert report.accepted
    assert report.view.combat is not None
    assert report.view.combat.status == "active"
    assert report.view.status == "running"


def test_travel_unknown_exit_rejected_with_placement_untouched(tmp_path) -> None:
    fx = _Fixture(tmp_path)
    report = fx.service.travel(
        TravelCommand(game_id=fx.game_id, actor_id=fx.hero, direction="west")
    )
    assert not report.accepted
    assert report.error_code == "unknown_exit"
    assert report.view.scene.name == "Ruined Courtyard"
    assert report.view.combat is None


def test_travel_rejected_when_combat_active(tmp_path) -> None:
    fx = _Fixture(tmp_path)
    fx.service.travel(
        TravelCommand(game_id=fx.game_id, actor_id=fx.hero, direction="north")
    )
    report = fx.service.travel(
        TravelCommand(game_id=fx.game_id, actor_id=fx.hero, direction="south")
    )
    assert not report.accepted
    assert report.error_code == "combat_active"


def test_view_without_world_has_no_scene() -> None:
    service = GameService(
        InMemoryGameRepository(InMemoryEventRepository()), InMemoryEventRepository()
    )
    game_id = service.create_game(CreateGameCommand(seed=1))
    assert service.get_view(game_id).scene is None


def test_scene_view_lists_exits_as_names(tmp_path) -> None:
    fx = _Fixture(tmp_path)
    view = fx.service.get_view(fx.game_id)
    assert view.scene is not None
    assert view.scene.exits == [("north", "Eastern Tower")]


def test_view_enemies_follow_the_scene(tmp_path) -> None:
    fx = _Fixture(tmp_path)

    at_courtyard = fx.service.get_view(fx.game_id)
    assert at_courtyard.enemies == []  # the goblin waits in the tower

    fx.service.travel(
        TravelCommand(game_id=fx.game_id, actor_id=fx.hero, direction="north")
    )

    at_tower = fx.service.get_view(fx.game_id)
    assert [enemy.name for enemy in at_tower.enemies] == ["Goblin Scout"]
