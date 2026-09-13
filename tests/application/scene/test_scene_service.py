"""SceneService: one agent action per tick, deterministic guards (Task 8)."""


from session import SessionConfig, build_session


def test_factory_wires_scene_service_when_world_and_agents_are_wired() -> None:
    session = build_session(
        SessionConfig(
            seed=42, agent_mode="fake", gm_mode="fake", world_path="world.toml"
        )
    )
    assert session.scene_service is not None


def test_invalid_scene_script_yields_idle_never_crash() -> None:
    session = build_session(
        SessionConfig(seed=42, agent_mode="fake", gm_mode="fake", world_path="world.toml")
    )
    assert session.scene_service is not None
    # Fake-scripted agents answer scene acts with the combat script (action_type
    # "talk" needs speech; "attack" is not a scene action): mapped to idle/reject.
    outcome = session.scene_service.tick(session.game_id)
    assert outcome.kind in {"idle", "scene_action"}


def test_travel_by_human_then_tick_waits_for_combat() -> None:
    from application.commands import TravelCommand

    session = build_session(
        SessionConfig(seed=42, agent_mode="fake", gm_mode="fake", world_path="world.toml")
    )
    assert session.scene_service is not None
    view = session.game_service.get_view(session.game_id)
    hero_id = view.party[0].id
    report = session.game_service.travel(
        TravelCommand(
            game_id=session.game_id,
            actor_id=_character_id(hero_id),
            direction="north",
        )
    )
    assert report.accepted and report.view.combat is not None
    outcome = session.scene_service.tick(session.game_id)
    assert outcome.kind == "combat_wait"


def _character_id(value: str):
    from domain.common.ids import CharacterId

    return CharacterId(value)
