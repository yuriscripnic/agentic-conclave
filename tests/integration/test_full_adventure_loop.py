"""Full-adventure loop, deterministic and offline (Task 9, Definition of Done).

Scene A: an agent talks; an agent travels north; combat auto-opens at the
tower; the fight auto-resolves; a post-combat agent talk still lands.
Zero network, zero keys (FakeModelGateway + scripted decisions).
"""

from typing import Any

import pytest

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.fake import FakeModelGateway
from ai.models.profiles import load_model_profiles
from application.agents.fake_script import ScriptedAgentGateway
from application.scene.scene_service import SceneLoopConfig, SceneService
from session import SessionConfig, advance, build_session, open_session
from session.factory import CONFIG_DIR


def _scene_script():
    """Queue: talk at the courtyard, then travel north."""
    calls = {"n": 0}

    def _decision() -> dict[str, Any]:
        calls["n"] += 1
        scripted = [
            {
                "action_type": "talk",
                "speech": "We should push toward the tower.",
                "public_message": "Mira glances at the northern path.",
            },
            {
                "action_type": "travel",
                "exit_direction": "north",
                "public_message": "Mira heads through the northern gate.",
            },
        ]
        return scripted[min(calls["n"] - 1, len(scripted) - 1)]

    return _decision


def _scene_service(session) -> SceneService:
    gateway = ScriptedAgentGateway(FakeModelGateway(), _scene_script())
    return SceneService(
        session.game_service,
        world=session.game_service._world,
        turn_service=session.turn_service,
        gm_director=session.gm_director,
        runtime=AgentRuntime(gateway, RetryPolicy()),
        model_catalog=load_model_profiles(CONFIG_DIR / "llm.toml"),
        config=SceneLoopConfig(tick_seconds=0.0, max_agent_scene_actions=4),
    )


def test_full_adventure_talk_travel_combat_talk() -> None:
    session = open_session(
        SessionConfig(seed=7, agent_mode="fake", gm_mode="fake", world_path="world.toml")
    )
    scene = _scene_service(session)

    # Beat 1: an agent talks in the courtyard opening scene
    tick = scene.tick(session.game_id)
    assert tick.kind == "scene_action"
    assert tick.public_message is not None

    # Beat 2: travel north → arrival → combat auto-opens deterministically
    tick = scene.tick(session.game_id)
    assert tick.travel_report is not None
    assert tick.travel_report.accepted
    view = tick.travel_report.view
    assert view.combat is not None and view.combat.status == "active"
    arrival_types = [e.event_type for e in tick.travel_report.events]
    assert "character_arrived" in arrival_types
    # The traveler is an agent; the party leader stayed behind, so the scene
    # view (which follows the leader) still shows the courtyard — correct.

    # Beat 3: the scene loop now waits on combat (pause rule)
    assert scene.tick(session.game_id).kind == "combat_wait"

    # Beat 4: the fight resolves through the normal combat drivers
    guard = 0
    while advance(session) is not None:
        guard += 1
        if guard > 400:
            pytest.fail("combat did not resolve within the turn guard")
    view = session.game_service.get_view(session.game_id)
    if view.status != "ended":
        # With fake combat scripts the game ends on the enemy/party chain;
        # some seeds leave the human alive — act for them until the fight ends.
        from application.commands import SubmitActionCommand

        for _attempt in range(400):
            view = session.game_service.get_view(session.game_id)
            if view.status == "ended":
                break
            combat = view.combat
            if combat is None or combat.status != "active":
                break
            hero = next(
                member
                for member in view.party
                if member.id == combat.active_actor_id
            )
            target = next(e.id for e in view.enemies if not e.is_defeated)
            report = session.game_service.submit_action(
                SubmitActionCommand(
                    game_id=session.game_id,
                    actor_id=_cid(hero.id),
                    action_type="attack",
                    target_id=_cid(target),
                )
            )
            assert report.accepted, report.reason
        else:
            pytest.fail("combat did not end while acting for the human")

    # Beat 5: post-combat the scene loop is usable again
    tick = scene.tick(session.game_id)
    assert tick.kind in {"scene_action", "game_over"}

    # Event audit: the adventure itself was recorded
    types = [e.event_type for e in session.game_service.get_events(session.game_id)]
    assert "character_arrived" in types
    assert "combat_started" in types
    assert "combat_ended" in types


def test_world_session_starts_in_exporation_not_combat() -> None:
    session = build_session(SessionConfig(seed=42, gm_mode="fake", world_path="world.toml"))
    view = session.game_service.get_view(session.game_id)
    assert view.status == "created"
    assert view.combat is None
    assert view.scene is not None
    assert view.scene.name == "Ruined Courtyard"


def _cid(value: str):
    from domain.common.ids import CharacterId

    return CharacterId(value)
