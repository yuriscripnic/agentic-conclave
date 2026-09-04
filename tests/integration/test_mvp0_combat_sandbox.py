# tests/integration/test_mvp0_combat_sandbox.py
"""MVP-0 end-to-end through the application layer — no LLM (Implementation Plan §26)."""

import pytest

from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.views import GameView
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


def _service() -> GameService:
    return GameService(InMemoryGameRepository(), InMemoryEventRepository())


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


def _new_game(
    service: GameService, seed: int
) -> tuple[GameId, CharacterId, CharacterId]:
    game_id = service.create_game(
        CreateGameCommand(seed=seed, campaign_name="The Forgotten Ruins")
    )
    arin_id = service.add_character(game_id, _arin())
    goblin_id = service.add_character(game_id, _goblin())
    service.start_combat(game_id)
    return game_id, arin_id, goblin_id


def _play(seed: int) -> tuple[GameService, GameId, GameView]:
    service = _service()
    game_id, arin_id, goblin_id = _new_game(service, seed)

    for _ in range(100):
        view = service.get_view(game_id)
        assert view.combat is not None
        if view.combat.status == "ended":
            break
        active = view.combat.active_actor_id
        assert active is not None
        if active == str(arin_id):
            report = service.submit_action(
                SubmitActionCommand(
                    game_id=game_id,
                    actor_id=arin_id,
                    action_type="attack",
                    target_id=goblin_id,
                )
            )
            assert report.accepted, f"party attack rejected: {report.reason}"
        else:
            service.run_active_enemy_turns(game_id)
    else:
        pytest.fail("combat did not end within 100 iterations")

    return service, game_id, service.get_view(game_id)


def test_mvp0_combat_reaches_a_deterministic_winner() -> None:
    service, game_id, view = _play(seed=42)

    assert view.status == "ended"
    assert view.combat is not None
    assert view.combat.status == "ended"

    ended = [
        e for e in service.get_events(game_id) if e.event_type == "combat_ended"
    ]
    assert len(ended) == 1
    winner = ended[0].payload["winner_side"]
    if winner == "party":
        assert all(c.is_defeated for c in view.enemies)
        assert any(not c.is_defeated for c in view.party)
    else:
        assert all(c.is_defeated for c in view.party)
        assert any(not c.is_defeated for c in view.enemies)


def test_events_have_contiguous_sequences() -> None:
    service, game_id, _ = _play(seed=42)
    sequences = [e.sequence for e in service.get_events(game_id)]
    assert sequences == list(range(1, len(sequences) + 1))


def test_mvp0_is_reproducible_for_the_same_seed() -> None:
    first_service, first_id, first_view = _play(seed=42)
    second_service, second_id, second_view = _play(seed=42)

    # UUIDs differ between runs, so compare the observable trajectory instead.
    first_types = [e.event_type for e in first_service.get_events(first_id)]
    second_types = [e.event_type for e in second_service.get_events(second_id)]
    assert first_types == second_types

    assert [
        (c.name, c.hp_current) for c in first_view.party + first_view.enemies
    ] == [(c.name, c.hp_current) for c in second_view.party + second_view.enemies]


def test_rejected_action_changes_nothing() -> None:
    service = _service()
    game_id, arin_id, goblin_id = _new_game(service, seed=1)
    view = service.get_view(game_id)
    assert view.combat is not None
    active = view.combat.active_actor_id
    assert active is not None
    # Always submit as the character whose turn it is NOT.
    if active == str(arin_id):
        actor_id, target_id = goblin_id, arin_id
    else:
        actor_id, target_id = arin_id, goblin_id

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
    after = service.get_view(game_id)
    assert after.combat is not None
    assert after.combat.active_actor_id == active
    for before_char, after_char in zip(
        view.party + view.enemies, after.party + after.enemies, strict=True
    ):
        assert before_char.hp_current == after_char.hp_current
