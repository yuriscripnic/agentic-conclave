"""The agent turn use case: decision-attempt loop over the model, fallback, reporting."""

from __future__ import annotations

from dataclasses import dataclass

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.runtime import AgentRuntime
from ai.memory.types import MemoryRecord
from ai.models.errors import ModelError
from ai.models.profiles import ModelProfileCatalog
from ai.models.types import LLMInvocation
from application.agents.character_agent import (
    ATTACK_DECISION_SCHEMA,
    AgentDecision,
    CharacterAgent,
    InvalidAgentDecisionError,
)
from application.agents.party_board import PartyMessage, PartyMessageBoard
from application.agents.perception import (
    AgentNotInCombatError,
    AgentPerception,
    build_perception,
    first_living_opponent,
)
from application.agents.profiles import AgentProfile, AgentProfileCatalog
from application.commands import SubmitActionCommand
from application.game_service import GameService
from application.memory.memory_service import MemoryService
from application.views import TurnReport
from domain.common.errors import PersistenceError
from domain.common.ids import CharacterId, GameId

_PARTY_CHATTER_LIMIT = 8


@dataclass(frozen=True)
class AgentTurnReport:
    actor_id: str
    actor_name: str
    accepted: bool
    proposal_source: str  # "model" | "fallback"
    action_attempts: int
    rejection_reasons: tuple[str, ...]
    fallback_reason: str | None
    public_message: str | None
    invocations: tuple[LLMInvocation, ...]
    turn_report: TurnReport
    party_message: str | None = None
    memory_retrieved: int = 0


class AgentNotRegisteredError(KeyError):
    """Raised when take_turn is called for an actor with no registered agent profile."""


class AgentTurnService:
    """Runs one agent-controlled turn: bounded decisions, engine validation, fallback."""

    def __init__(
        self,
        game_service: GameService,
        runtime: AgentRuntime,
        catalog: ModelProfileCatalog,
        agent_profiles: AgentProfileCatalog,
        *,
        max_action_retries: int | None = None,
        board: PartyMessageBoard | None = None,
        memory: MemoryService | None = None,
    ) -> None:
        self._game_service = game_service
        self._runtime = runtime
        self._catalog = catalog
        self._max_action_retries = (
            max_action_retries
            if max_action_retries is not None
            else agent_profiles.max_action_retries
        )
        self._board = board if board is not None else PartyMessageBoard()
        self._memory = memory
        self._agents: dict[str, AgentProfile] = {}

    def register(self, actor_id: CharacterId, profile: AgentProfile) -> None:
        self._agents[actor_id.value] = profile

    def is_agent_controlled(self, actor_id: CharacterId) -> bool:
        return actor_id.value in self._agents

    def take_turn(self, game_id: GameId, actor_id: CharacterId) -> AgentTurnReport:
        profile = self._agents.get(actor_id.value)
        if profile is None:
            raise AgentNotRegisteredError(actor_id.value)

        agent = CharacterAgent(profile)
        model_profile = self._catalog.get(profile.model_profile)
        invocations: list[LLMInvocation] = []
        rejection_reasons: list[str] = []
        rejection: str | None = None

        # Rejected actions never mutate game state (§28), so one perception serves
        # every attempt; hoisting it also makes memory retrieval once-per-turn.
        view = self._game_service.get_view(game_id)
        perception = build_perception(view, actor_id.value)
        memories = self._retrieve_memories(game_id, perception, invocations)

        for attempt in range(1, self._max_action_retries + 2):
            try:
                response = self._runtime.decide_structured(
                    profile=model_profile,
                    system=agent.build_system_prompt(),
                    user=agent.build_user_prompt(
                        perception,
                        rejection=rejection,
                        party_messages=self._board.recent(_PARTY_CHATTER_LIMIT),
                        memories=memories,
                    ),
                    schema=ATTACK_DECISION_SCHEMA,
                )
                invocations.append(response.invocation)
                decision = agent.map_decision(response.data, perception)
            except AgentRuntimeMisconfiguredError:
                raise
            except AgentRuntimeError as error:
                if error.last_invocation is not None:
                    invocations.append(error.last_invocation)
                rejection = f"model failure: {error}"
                rejection_reasons.append(rejection)
                continue
            except InvalidAgentDecisionError as error:
                rejection = str(error)
                rejection_reasons.append(rejection)
                continue

            turn_report = self._submit(game_id, actor_id, decision)
            if turn_report.accepted:
                if decision.party_message is not None:
                    self._board.post(
                        PartyMessage(
                            actor_name=perception.self_view.name,
                            text=decision.party_message,
                            round_number=perception.round_number,
                        )
                    )
                self._record_memories(
                    game_id, perception, turn_report, decision.memory_note, invocations
                )
                return AgentTurnReport(
                    actor_id=actor_id.value,
                    actor_name=perception.self_view.name,
                    accepted=True,
                    proposal_source="model",
                    action_attempts=attempt,
                    rejection_reasons=tuple(rejection_reasons),
                    fallback_reason=None,
                    public_message=decision.public_message,
                    invocations=tuple(invocations),
                    turn_report=turn_report,
                    party_message=decision.party_message,
                    memory_retrieved=len(memories),
                )
            rejection = turn_report.reason or "action rejected by the rules engine"
            rejection_reasons.append(rejection)

        return self._fallback(
            game_id,
            actor_id,
            perception,
            memories,
            invocations,
            tuple(rejection_reasons),
        )

    def _submit(
        self, game_id: GameId, actor_id: CharacterId, decision: AgentDecision
    ) -> TurnReport:
        return self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=decision.proposal.target_id,
            )
        )

    def _fallback(
        self,
        game_id: GameId,
        actor_id: CharacterId,
        perception: AgentPerception,
        memories: tuple[MemoryRecord, ...],
        invocations: list[LLMInvocation],
        rejection_reasons: tuple[str, ...],
    ) -> AgentTurnReport:
        view = self._game_service.get_view(game_id)
        target_id = first_living_opponent(view, actor_id.value)
        if target_id is None:
            raise AgentNotInCombatError(
                f"character {actor_id.value} has no living opponent to attack"
            )
        detail = "; ".join(rejection_reasons) if rejection_reasons else "no model decision"
        turn_report = self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=CharacterId(target_id),
            )
        )
        self._record_memories(game_id, perception, turn_report, None, invocations)
        return AgentTurnReport(
            actor_id=actor_id.value,
            actor_name=perception.self_view.name,
            accepted=turn_report.accepted,
            proposal_source="fallback",
            action_attempts=self._max_action_retries + 1,
            rejection_reasons=rejection_reasons,
            fallback_reason=f"decision budget exhausted ({detail})",
            public_message=None,
            invocations=tuple(invocations),
            turn_report=turn_report,
            party_message=None,
            memory_retrieved=len(memories),
        )

    def _retrieve_memories(
        self,
        game_id: GameId,
        perception: AgentPerception,
        invocations: list[LLMInvocation],
    ) -> tuple[MemoryRecord, ...]:
        """Memory never gates a turn (spec §2.8): failures degrade to no memories."""
        if self._memory is None:
            return ()
        try:
            return self._memory.retrieve(str(game_id), perception)
        except ModelError as error:
            if error.invocation is not None:
                invocations.append(error.invocation)
            return ()
        except PersistenceError:
            return ()

    def _record_memories(
        self,
        game_id: GameId,
        perception: AgentPerception,
        turn_report: TurnReport,
        note: str | None,
        invocations: list[LLMInvocation],
    ) -> None:
        """Recording never revisits an accepted action (spec §2.8): failures drop the write."""
        if self._memory is None:
            return
        try:
            self._memory.record_turn(str(game_id), perception, turn_report, note=note)
        except ModelError as error:
            if error.invocation is not None:
                invocations.append(error.invocation)
        except PersistenceError:
            return
