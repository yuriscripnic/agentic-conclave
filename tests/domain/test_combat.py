# tests/domain/test_combat.py
from collections.abc import Sequence

import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.combat.engine import CombatEngine
from domain.combat.policy import SimpleMeleeEnemyPolicy
from domain.combat.state import Combat, CombatStatus, InitiativeEntry, roll_initiative
from domain.common.errors import AgentDecisionFailedError, ValidationError
from domain.common.ids import CampaignId, CharacterId, GameId
from domain.events.collector import EventCollector
from domain.rules.actions import ActionEconomy, AttackProposal
from domain.rules.dice import DiceRoller
from domain.space.board import Board, Spawns
from domain.space.square import Square
from domain.world.game import Game


def _seed_with_rolls(rolls: list[int]) -> int:
    """Find a seed whose d20 sequence equals `rolls` (deterministic test helper)."""
    for seed in range(100_000):
        roller = DiceRoller(seed=seed)
        if [roller.roll_d20().natural for _ in rolls] == rolls:
            return seed
    raise AssertionError("no seed produced the requested rolls")


def _weapon(weapon_id: str, name: str, die_size: int) -> Weapon:
    return Weapon(
        weapon_id=weapon_id, name=name, damage_die_count=1, damage_die_size=die_size
    )


def _fighter(name: str = "Arin") -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=CharacterType.PLAYER_CHARACTER,
        character_class=CharacterClass.FIGHTER,
        level=1,
        ability_scores=AbilityScores(
            strength=16,
            dexterity=13,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=9,
        ),
        armor_class=16,
        speed_ft=30,
        hit_points=HitPoints(current=12, maximum=12),
        equipped_weapon=_weapon("longsword", "Longsword", 8),
    )


def _goblin(name: str = "Goblin", hp: int = 7) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=CharacterType.MONSTER,
        character_class=None,
        level=1,
        ability_scores=AbilityScores(
            strength=8,
            dexterity=14,
            constitution=10,
            intelligence=10,
            wisdom=8,
            charisma=8,
        ),
        armor_class=13,
        speed_ft=30,
        hit_points=HitPoints(current=hp, maximum=hp),
        equipped_weapon=_weapon("scimitar", "Scimitar", 6),
    )


def _game(*members: Character) -> Game:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )
    for member in members:
        if member.character_type is CharacterType.MONSTER:
            game.add_enemy(member)
        else:
            game.add_party_member(member)
    return game


def _start(
    dice: DiceRoller,
    game: Game,
    board: Board | None = None,
    spawns: Spawns | None = None,
    participants: Sequence[CharacterId] | None = None,
) -> tuple[CombatEngine, Combat, EventCollector]:
    engine = CombatEngine(dice)
    collector = EventCollector(game_id=game.game_id)
    if participants is None:
        participants = (*game.party_ids, *game.enemy_ids)
    combat = engine.start(game, participants, collector, board=board, spawns=spawns)
    return engine, combat, collector


def test_initiative_orders_by_total_then_dex_modifier() -> None:
    low_dex = _fighter("Slow")
    high_dex = _goblin("Quick")
    characters = {low_dex.id: low_dex, high_dex.id: high_dex}
    order = [low_dex.id, high_dex.id]

    mirror = DiceRoller(seed=11)
    raw = [mirror.roll_d20().natural for _ in order]
    dex_mods = [1, 2]  # dex 13 -> +1, dex 14 -> +2
    ranking = sorted(
        zip(order, raw, dex_mods, strict=True),
        key=lambda entry: (-(entry[1] + entry[2]), -entry[2]),
    )
    expected = [entry[0] for entry in ranking]

    entries = roll_initiative(DiceRoller(seed=11), characters, order)
    assert [entry.character_id for entry in entries] == expected


def test_start_emits_initiative_combat_started_and_turn_started() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=7), game)

    types = [e.event_type for e in collector.events]
    assert types.count("initiative_rolled") == 2
    assert "combat_started" in types
    assert types[-1] == "turn_started"
    assert combat.status is CombatStatus.ACTIVE
    assert combat.active_actor() == combat.entries[0].character_id
    assert combat.round_number == 1


def test_validate_rejects_when_not_your_turn() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    idle = (
        game.enemy_ids[0]
        if combat.active_actor() == game.party_ids[0]
        else game.party_ids[0]
    )
    proposal = AttackProposal(actor_id=idle, target_id=combat.active_actor())

    result = engine.validate(game, combat, proposal)
    assert result.valid is False
    assert result.error_code == "not_your_turn"


def test_validate_rejects_unknown_same_side_or_defeated_targets() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    actor = game.characters[combat.active_actor()]
    opponents = game.opponents_of(actor.id)

    # unknown target
    unknown = AttackProposal(actor_id=actor.id, target_id=CharacterId.generate())
    assert engine.validate(game, combat, unknown).error_code == "invalid_target"

    # self target
    himself = AttackProposal(actor_id=actor.id, target_id=actor.id)
    assert engine.validate(game, combat, himself).error_code == "invalid_target"

    # same side target
    same_side_id = (
        game.party_ids[0] if actor.id in game.party_ids else game.enemy_ids[0]
    )
    ally = AttackProposal(actor_id=actor.id, target_id=same_side_id)
    if ally.target_id != actor.id:
        assert engine.validate(game, combat, ally).error_code == "invalid_target"

    # defeated target
    victim = game.characters[opponents[0]]
    victim.apply_damage(999)
    dead = AttackProposal(actor_id=actor.id, target_id=victim.id)
    assert engine.validate(game, combat, dead).error_code == "invalid_target"


def test_validate_rejects_when_action_already_used() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    actor_id = combat.active_actor()
    target = game.opponents_of(actor_id)[0]

    combat.economy.action_taken = True
    result = engine.validate(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target)
    )
    assert result.error_code == "action_unavailable"


def test_validate_rejects_when_combat_ended() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, _ = _start(DiceRoller(seed=7), game)
    combat.status = CombatStatus.ENDED
    result = engine.validate(
        game,
        combat,
        AttackProposal(
            actor_id=combat.active_actor(), target_id=CharacterId.generate()
        ),
    )
    assert result.error_code == "combat_not_active"


def test_resolve_rejection_records_event_and_mutates_nothing() -> None:
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=7), game)
    actor_id = combat.active_actor()
    opponent = game.opponents_of(actor_id)[0]
    proposal = AttackProposal(actor_id=opponent, target_id=actor_id)  # wrong turn
    hp_before = game.characters[opponent].hit_points.current

    result = engine.resolve(game, combat, proposal, collector)

    assert result.valid is False
    assert collector.events[-1].event_type == "action_rejected"
    assert combat.economy.action_taken is False
    assert game.characters[opponent].hit_points.current == hp_before


def test_resolve_hit_applies_damage_and_consumes_action() -> None:
    # Rolls: initiative d20s (fighter's 16 beats the goblin's 10 through the DEX
    # tiebreak), then a d20 of 15 (hits AC 13 with +5 bonus).
    seed = _seed_with_rolls([16, 10, 15])
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    result = engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    assert result.valid is True
    assert combat.economy.action_taken is True
    resolved = [e for e in collector.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["hit"] is True
    damage_events = [e for e in collector.events if e.event_type == "damage_applied"]
    assert damage_events, "a hit must apply damage"
    payload = damage_events[-1].payload
    assert payload["hp_before"] - payload["hp_after"] == payload["amount"]
    assert game.characters[target_id].hit_points.current == payload["hp_after"]


def test_resolve_critical_hit_doubles_damage_dice() -> None:
    # Rolls: initiative d20s (fighter first), then a natural 20.
    seed = _seed_with_rolls([16, 10, 20])
    game = _game(_fighter(), _goblin(hp=100))
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    resolved = [e for e in collector.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["critical"] is True
    damage = [e for e in collector.events if e.event_type == "damage_applied"][-1]
    # 2d8 + 3 with advantage doubled dice must exceed any single-die roll of 1d8+3
    assert damage.payload["amount"] >= 5


def test_resolve_natural_one_always_misses() -> None:
    seed = _seed_with_rolls([16, 10, 1])
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    resolved = [e for e in collector.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["hit"] is False
    assert not [e for e in collector.events if e.event_type == "damage_applied"]
    assert game.characters[target_id].hit_points.current == 7


def test_defeated_target_emits_character_defeated() -> None:
    seed = _seed_with_rolls([16, 10, 15])
    game = _game(_fighter(), _goblin(hp=1))
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    defeated = collector.events[-1]
    assert defeated.event_type == "character_defeated"
    assert defeated.payload["character_id"] == str(target_id)


def test_advance_turn_skips_defeated_actors() -> None:
    game = _game(_fighter("A"), _goblin("G1"), _goblin("G2"))
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.party_ids[0],
                total=10,
                dexterity_modifier=1,
                tiebreaker=5,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[0],
                total=8,
                dexterity_modifier=2,
                tiebreaker=3,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[1],
                total=6,
                dexterity_modifier=2,
                tiebreaker=2,
            ),
        ],
        economy=ActionEconomy(movement_budget_ft=30),
    )
    game.characters[game.enemy_ids[0]].apply_damage(999)  # G1 defeated
    collector = EventCollector(game_id=game.game_id)
    engine = CombatEngine(DiceRoller(seed=1))

    engine.advance_turn(game, combat, collector)

    assert combat.turn_index == 2
    assert combat.active_actor() == game.enemy_ids[1]


def test_advance_wraps_and_increments_round() -> None:
    game = _game(_fighter(), _goblin())
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.party_ids[0],
                total=10,
                dexterity_modifier=1,
                tiebreaker=5,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[0],
                total=8,
                dexterity_modifier=2,
                tiebreaker=3,
            ),
        ],
        economy=ActionEconomy(movement_budget_ft=30),
        round_number=1,
        turn_index=1,
    )
    collector = EventCollector(game_id=game.game_id)
    engine = CombatEngine(DiceRoller(seed=1))

    engine.advance_turn(game, combat, collector)

    assert combat.round_number == 2
    assert combat.active_actor() == game.party_ids[0]
    assert combat.economy.action_taken is False
    assert collector.events[-1].event_type == "turn_started"


def test_advance_ends_combat_when_a_side_is_wiped() -> None:
    game = _game(_fighter(), _goblin())
    game.characters[game.enemy_ids[0]].apply_damage(999)
    combat = Combat(
        entries=[
            InitiativeEntry(
                character_id=game.party_ids[0],
                total=10,
                dexterity_modifier=1,
                tiebreaker=5,
            ),
            InitiativeEntry(
                character_id=game.enemy_ids[0],
                total=8,
                dexterity_modifier=2,
                tiebreaker=3,
            ),
        ],
        economy=ActionEconomy(movement_budget_ft=30),
        turn_index=0,
    )
    collector = EventCollector(game_id=game.game_id)
    engine = CombatEngine(DiceRoller(seed=1))

    engine.advance_turn(game, combat, collector)

    assert combat.status is CombatStatus.ENDED
    ended = collector.events[-1]
    assert ended.event_type == "combat_ended"
    assert ended.payload["winner_side"] == "party"


def test_enemy_policy_targets_first_living_opponent() -> None:
    game = _game(_fighter("A"), _goblin("G1"), _goblin("G2"))
    policy = SimpleMeleeEnemyPolicy()

    proposal = policy.decide(game, game.enemy_ids[0])
    assert proposal.target_id == game.party_ids[0]


def test_enemy_policy_raises_without_living_opponents() -> None:
    game = _game(_fighter("A"), _goblin("G"))
    game.characters[game.party_ids[0]].apply_damage(999)
    policy = SimpleMeleeEnemyPolicy()

    with pytest.raises(AgentDecisionFailedError):
        policy.decide(game, game.enemy_ids[0])


def test_initiative_ties_preserve_participant_order() -> None:
    first = _fighter("First")
    second = _fighter("Second")
    characters = {first.id: first, second.id: second}
    order = [first.id, second.id]
    seed = _seed_with_rolls([7, 7])  # equal naturals, equal dex mods (+1 each)

    entries = roll_initiative(DiceRoller(seed=seed), characters, order)

    assert [entry.character_id for entry in entries] == order
    assert entries[0].total == entries[1].total == 8


def _spawns() -> Spawns:
    return Spawns(
        party=(Square(0, 0), Square(0, 1), Square(0, 2)),
        enemies=(Square(4, 0), Square(4, 1), Square(4, 2)),
    )


def _board() -> Board:
    return Board(width=5, height=5)


def test_start_places_participants_on_spawn_squares_in_list_order() -> None:
    game = _game(_fighter(), _goblin())
    _, combat, _ = _start(DiceRoller(seed=1), game, board=_board(), spawns=_spawns())
    assert combat.positions[game.party_ids[0]] == Square(0, 0)
    assert combat.positions[game.enemy_ids[0]] == Square(4, 0)


def test_start_without_a_board_leaves_positions_empty() -> None:
    game = _game(_fighter(), _goblin())
    _, combat, _ = _start(DiceRoller(seed=1), game)
    assert combat.positions == {}
    assert combat.board is None


def test_more_participants_than_spawns_is_rejected() -> None:
    game = _game(_fighter("A"), _fighter("B"), _goblin())
    spawns = Spawns(party=(Square(0, 0),), enemies=(Square(4, 0),))
    with pytest.raises(ValidationError):
        _start(DiceRoller(seed=1), game, board=_board(), spawns=spawns)


def test_duplicate_spawn_squares_are_rejected() -> None:
    game = _game(_fighter(), _goblin())
    spawns = Spawns(party=(Square(0, 0),), enemies=(Square(0, 0),))
    with pytest.raises(ValidationError):
        _start(DiceRoller(seed=1), game, board=_board(), spawns=spawns)


def test_spawn_on_a_wall_is_rejected() -> None:
    game = _game(_fighter(), _goblin())
    board = Board(width=5, height=5, walls=frozenset({Square(4, 0)}))
    with pytest.raises(ValidationError):
        _start(DiceRoller(seed=1), game, board=board, spawns=_spawns())


def test_participant_absent_from_both_rosters_is_rejected() -> None:
    game = _game(_fighter(), _goblin())
    stray = _goblin("Stray")
    game.characters[stray.id] = stray  # in the roster, on neither side
    with pytest.raises(ValidationError):
        _start(
            DiceRoller(seed=1),
            game,
            board=_board(),
            spawns=_spawns(),
            participants=(*game.party_ids, *game.enemy_ids, stray.id),
        )
