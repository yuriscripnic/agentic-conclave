"""Memory policy: derive, embed, store, and retrieve one agent's memories (spec §3.3)."""

from __future__ import annotations

import asyncio
import uuid

from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.memory.types import EmbeddingRequest, MemoryKind, MemoryRecord
from application.agents.perception import AgentPerception
from application.views import TurnReport

_RETRIEVAL_LIMIT = 5


class MemoryService:
    """Coordinates the embedding gateway and the memory repository for a game's agents."""

    def __init__(
        self,
        gateway: EmbeddingGateway,
        repository: MemoryRepository,
        *,
        model: str,
        retrieval_limit: int = _RETRIEVAL_LIMIT,
    ) -> None:
        self._gateway = gateway
        self._repository = repository
        self._model = model
        self._retrieval_limit = retrieval_limit

    def retrieve(
        self, game_id: str, perception: AgentPerception
    ) -> tuple[MemoryRecord, ...]:
        """Embed the situation line and return the agent's most relevant memories."""
        me = perception.self_view
        opponent_names = (
            ", ".join(opponent.name for opponent in perception.opponents) or "none"
        )
        query = (
            f"{me.name} the {me.character_class}; "
            f"round {perception.round_number}; opponents: {opponent_names}"
        )
        response = asyncio.run(
            self._gateway.embed(EmbeddingRequest(texts=(query,), model=self._model))
        )
        return self._repository.search(
            game_id, me.id, response.vectors[0], limit=self._retrieval_limit
        )

    def record_turn(
        self,
        game_id: str,
        perception: AgentPerception,
        turn_report: TurnReport,
        *,
        note: str | None = None,
    ) -> None:
        """Record this turn's episodic (events) and semantic (note) memories."""
        if not turn_report.accepted:
            return
        entries: list[tuple[MemoryKind, str]] = []
        episode = _episodic_text(perception, turn_report)
        if episode is not None:
            entries.append((MemoryKind.EPISODIC, episode))
        if note is not None:
            entries.append((MemoryKind.SEMANTIC, note))
        if not entries:
            return
        response = asyncio.run(
            self._gateway.embed(
                EmbeddingRequest(
                    texts=tuple(text for _, text in entries), model=self._model
                )
            )
        )
        for (kind, text), vector in zip(entries, response.vectors, strict=True):
            self._repository.append(
                MemoryRecord(
                    memory_id=uuid.uuid4().hex,
                    game_id=game_id,
                    agent_key=perception.self_view.id,
                    kind=kind,
                    text=text,
                    round_number=perception.round_number,
                    embedding=vector,
                )
            )


def _episodic_text(perception: AgentPerception, turn_report: TurnReport) -> str | None:
    """One deterministic line from the executed turn's domain events (spec Decision 6)."""
    names = {opponent.id: opponent.name for opponent in perception.opponents}
    names[perception.self_view.id] = perception.self_view.name
    attack: dict[str, object] | None = None
    target_id: str | None = None
    damage_total = 0
    defeated: set[str] = set()
    for envelope in turn_report.events:
        payload = envelope.payload
        if (
            envelope.event_type == "attack_resolved"
            and payload.get("attacker_id") == perception.self_view.id
        ):
            attack = payload
            target_id = str(payload.get("target_id"))
        elif envelope.event_type == "damage_applied":
            # Damage from the enemy chain targets party members; only damage to
            # this attack's target is attributable to the actor (spec Decision 6).
            if target_id is not None and str(payload.get("character_id")) == target_id:
                damage_total += int(str(payload.get("amount", 0)))
        elif envelope.event_type == "character_defeated":
            defeated.add(str(payload.get("character_id")))
    if attack is None or target_id is None:
        return None
    target = names.get(target_id, target_id)
    if attack.get("hit"):
        text = (
            f"Round {perception.round_number}: attacked {target} "
            f"and dealt {damage_total} damage"
        )
        if attack.get("critical"):
            text += " (critical)"
    else:
        text = f"Round {perception.round_number}: attacked {target} and missed"
    if target_id in defeated:
        text += f"; {target} fell"
    return text + "."
