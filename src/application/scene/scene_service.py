"""Scene loop: one agent-controlled scene action per tick, fully deterministic guards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.agents.runtime import AgentRuntime
from ai.models.profiles import ModelProfileCatalog
from application.agents.agent_turn_service import AgentTurnService
from application.agents.scene_decisions import (
    SCENE_DECISION_SCHEMA,
    InvalidSceneDecisionError,
    SceneDecision,
    map_scene_decision,
    validate_scene_decision,
)
from application.commands import TravelCommand
from application.gm.director import GmDirector
from application.telemetry import new_correlation_id
from application.views import GameView, TurnReport
from domain.common.ids import CharacterId, GameId
from domain.world.game import Game
from domain.world.locations import WorldMap


@dataclass(frozen=True)
class SceneLoopConfig:
    tick_seconds: float = 0.0
    max_agent_scene_actions: int = 4


@dataclass(frozen=True)
class SceneTick:
    """One out-of-combat scene step, ready for the interface to render."""

    kind: str  # "game_over" | "combat_wait" | "scene_action" | "idle"
    actor_name: str | None = None
    narration: str | None = None  # GM reply for a talk action
    public_message: str | None = None
    travel_report: TurnReport | None = None


class SceneService:
    """Drives out-of-combat autonomy; every legality check stays deterministic."""

    def __init__(
        self,
        game_service: Any,  # GameService; avoids a factory import cycle
        *,
        world: WorldMap,
        turn_service: AgentTurnService | None,
        gm_director: GmDirector | None,
        runtime: AgentRuntime,
        model_catalog: ModelProfileCatalog,
        model_profile: str = "player",
        config: SceneLoopConfig | None = None,
    ) -> None:
        self._game_service = game_service
        self._world = world
        self._turn_service = turn_service
        self._gm_director = gm_director
        self._runtime = runtime
        self._model_catalog = model_catalog
        self._model_profile = model_profile
        self._config = config or SceneLoopConfig()
        self._rejections = 0

    @property
    def tick_seconds(self) -> float:
        """Pacing between agent scene actions (config/game.toml [loop])."""
        return self._config.tick_seconds  # consecutive rejected/invalid proposals (§28 cap)

    def tick(self, game_id: GameId) -> SceneTick:
        """Advance the scene by ONE agent action (or report why nothing happens)."""
        view = self._game_service.get_view(game_id)
        if view.status == "ended":
            return SceneTick(kind="game_over")
        if view.combat is not None and view.combat.status == "active":
            return SceneTick(kind="combat_wait")
        if self._turn_service is None:
            return SceneTick(kind="idle")

        actor_id = self._next_agent(view, game_id)
        if actor_id is None:
            return SceneTick(kind="idle")
        actor_name = _name_of(view, actor_id)

        decision = self._decide(view, actor_id)
        if decision is None:
            return SceneTick(kind="idle")
        game: Game = self._game_service._game(game_id)
        reason = validate_scene_decision(decision, game, self._world, actor_id)
        if reason is not None:
            return self._rejected(actor_name, decision)

        if decision.action_type == "travel":
            report = self._game_service.travel(
                TravelCommand(
                    game_id=game_id,
                    actor_id=CharacterId(actor_id),
                    direction=decision.exit_direction or "",
                )
            )
            if not report.accepted:
                return self._rejected(actor_name, decision, report)
            return SceneTick(
                kind="scene_action",
                actor_name=actor_name,
                public_message=decision.public_message,
                travel_report=report,
            )

        if decision.action_type == "wait":
            self._rejections = 0
            return SceneTick(
                kind="scene_action",
                actor_name=actor_name,
                public_message=decision.public_message,
            )

        # talk → route through the same GM NPC-reply path as the human `say`.
        assert decision.speech is not None
        if self._gm_director is None:
            return SceneTick(
                kind="scene_action",
                actor_name=actor_name,
                public_message=decision.public_message,
            )
        gm_result = self._gm_director.on_player_say(
            game_id,
            f"{actor_name}: {decision.speech}",
            correlation_id=new_correlation_id(),
        )
        return SceneTick(
            kind="scene_action",
            actor_name=actor_name,
            public_message=decision.public_message,
            narration=gm_result.npc_reply or gm_result.narration,
        )

    # -- internals ---------------------------------------------------------

    def _rejected(
        self,
        actor_name: str,
        decision: SceneDecision,
        report: TurnReport | None = None,
    ) -> SceneTick:
        self._rejections += 1
        # Exhausted budget → deterministically skip this actor's scene action
        # (§28 fallback policy is "await the human", i.e. an idle tick).
        if self._rejections > self._config.max_agent_scene_actions:
            return SceneTick(kind="idle")
        return SceneTick(
            kind="scene_action",
            actor_name=actor_name,
            public_message=decision.public_message,
            travel_report=report,
        )

    def _next_agent(self, view: GameView, game_id: GameId) -> str | None:
        agent = self._turn_service
        assert agent is not None
        here = view.scene.location_id if view.scene is not None else None
        if here is None:
            return None
        game = self._game_service._game(game_id)
        for member in view.party:
            if member.is_defeated:
                continue
            if not agent.is_agent_controlled(CharacterId(member.id)):
                continue
            placement = game.location_of(CharacterId(member.id))
            if placement is not None and str(placement) == here:
                return member.id
        return None

    def _decide(self, view: GameView, actor_id: str) -> SceneDecision | None:
        try:
            model_profile = self._model_catalog.get(self._model_profile)
            response = self._runtime.decide_structured(
                profile=model_profile,
                system=self._scene_system_prompt(),
                user=self._scene_user_prompt(view, actor_id),
                schema=SCENE_DECISION_SCHEMA,
            )
        except Exception:  # ModelError → idle; never gates the game
            return None
        try:
            return map_scene_decision(response.data)
        except InvalidSceneDecisionError:
            return None

    def _scene_system_prompt(self) -> str:
        return (
            "You control a character exploring an adventure scene between fights.\n"
            "Choose exactly one action_type:\n"
            "- travel: move through one named exit (set exit_direction to the exit's direction).\n"
            "- talk: speak (set speech); an NPC may answer.\n"
            "- wait: do nothing this beat.\n"
            "Always fill public_message with one short line your character says aloud.\n"
        )

    def _scene_user_prompt(self, view: GameView, actor_id: str) -> str:
        scene = view.scene
        assert scene is not None
        lines = [
            f"You are {_name_of(view, actor_id)}.",
            f"Scene: {scene.name} — {scene.description}",
            "Exits:",
        ]
        lines.extend(f"- {d} -> {dest}" for d, dest in scene.exits)
        lines.append("Party present:")
        lines.extend(
            f"- {member.name} ({member.character_class or '?'})"
            for member in view.party
            if not member.is_defeated
        )
        return "\n".join(lines)


def _name_of(view: GameView, character_id: str) -> str:
    for member in (*view.party, *view.enemies):
        if member.id == character_id:
            return member.name
    return character_id
