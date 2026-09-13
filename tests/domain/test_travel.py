"""TravelService is deterministic; rejections never mutate state."""


from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.common.ids import CampaignId, CharacterId, GameId, LocationId
from domain.events.collector import EventCollector
from domain.world.game import Game
from domain.world.locations import Location, LocationExit, WorldMap
from domain.world.travel import TravelProposal, TravelService


def _location(name: str) -> Location:
    return Location(
        id=LocationId.generate(),
        name=name,
        description=f"The {name}.",
        exits=(),
    )


def _world() -> tuple[WorldMap, Location]:
    tower = _location("Tower")
    courtyard = Location(
        id=LocationId.generate(),
        name="Courtyard",
        description="The Courtyard.",
        exits=(LocationExit(direction="north", destination=tower.id),),
    )
    world = WorldMap(
        locations={courtyard.id: courtyard, tower.id: tower},
        start_id=courtyard.id,
    )
    return world, courtyard


def _member(name: str, character_type: CharacterType) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=character_type,
        character_class=CharacterClass.FIGHTER
        if character_type is CharacterType.PLAYER_CHARACTER
        else None,
        level=1,
        ability_scores=AbilityScores(
            strength=10, dexterity=10, constitution=10,
            intelligence=10, wisdom=10, charisma=10,
        ),
        armor_class=13,
        speed_ft=30,
        hit_points=HitPoints(current=10, maximum=10),
    )


def _game(world: WorldMap) -> tuple[Game, Character]:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )
    hero = _member("Arin", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(hero)
    game.mark_started()
    game.place(hero.id, world.start_id)
    return game, hero


def test_travel_moves_actor_and_records_arrival() -> None:
    world, _start = _world()
    tower = next(
        exit_.destination for exit_ in world.get(world.start_id).exits
    )
    game, hero = _game(world)
    collector = EventCollector(game_id=game.game_id)
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=hero.id, direction="north"),
        combat_active=False, collector=collector,
    )

    assert outcome.accepted
    assert outcome.location is not None and outcome.location.id == tower
    assert game.location_of(hero.id) == tower
    arrival = collector.events[-1]
    assert arrival.event_type == "character_arrived"
    assert arrival.payload["character_id"] == str(hero.id)
    assert arrival.payload["to_location_id"] == str(tower)


def test_rejected_unknown_exit_never_mutates_state() -> None:
    world, tower = _world()
    game, hero = _game(world)
    collector = EventCollector(game_id=game.game_id)
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=hero.id, direction="west"),
        combat_active=False, collector=collector,
    )

    assert not outcome.accepted and outcome.reason == "unknown_exit"
    assert game.location_of(hero.id) == world.start_id
    assert collector.events[-1].event_type == "action_rejected"


def test_rejected_during_combat_never_mutates_state() -> None:
    world, tower = _world()
    game, hero = _game(world)
    collector = EventCollector(game_id=game.game_id)
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=hero.id, direction="north"),
        combat_active=True, collector=collector,
    )

    assert not outcome.accepted and outcome.reason == "combat_active"
    assert game.location_of(hero.id) == world.start_id


def test_unknown_actor_rejected() -> None:
    world, tower = _world()
    game, _ = _game(world)
    collector = EventCollector(game_id=game.game_id)
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=CharacterId.generate(), direction="north"),
        combat_active=False, collector=collector,
    )
    assert not outcome.accepted and outcome.reason == "unknown_character"


def test_defeated_actor_rejected() -> None:
    world, tower = _world()
    game, hero = _game(world)
    hero.apply_damage(10)
    collector = EventCollector(game_id=game.game_id)
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=hero.id, direction="north"),
        combat_active=False, collector=collector,
    )
    assert not outcome.accepted and outcome.reason == "unknown_character"


def test_unplaced_actor_cannot_travel() -> None:
    world, tower = _world()
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )
    hero = _member("Brix", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(hero)
    game.mark_started()
    collector = EventCollector(game_id=game.game_id)
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=hero.id, direction="north"),
        combat_active=False, collector=collector,
    )
    assert not outcome.accepted and outcome.reason == "unknown_exit"
