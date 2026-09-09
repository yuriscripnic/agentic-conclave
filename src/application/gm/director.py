"""GM director: notable-event digest, prompts, response mapping, hook service.

The GM proposes nothing that mutates game state (spec D1/D2): it observes
views and events and produces narration. All game authority stays in the
domain/rules engine (CLAUDE.md §1, §10).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.gm.conversation import GmMessage
from application.gm.profiles import GmProfile
from application.views import GameView, TurnReport
from domain.events.collector import EventEnvelope

_NOTABLE_EVENT_TYPES = frozenset({"character_defeated", "combat_ended"})


def _is_notable(envelope: EventEnvelope) -> bool:
    """True for critical hits, defeats, and combat end only (spec D4)."""
    if envelope.event_type in _NOTABLE_EVENT_TYPES:
        return True
    return (
        envelope.event_type == "attack_resolved"
        and envelope.payload.get("critical") is True
    )


def notable_events(report: TurnReport) -> list[EventEnvelope]:
    """The notable events in a turn report (spec D4)."""
    return [envelope for envelope in report.events if _is_notable(envelope)]


def digest_lines(
    events: list[EventEnvelope], name_by_id: dict[str, str]
) -> list[str]:
    """Plain-text digest lines for the notable events in `events` (spec §3.4)."""
    lines: list[str] = []
    for envelope in events:
        if not _is_notable(envelope):
            continue
        payload = envelope.payload
        if envelope.event_type == "attack_resolved":
            attacker = name_by_id.get(
                str(payload["attacker_id"]), str(payload["attacker_id"])
            )
            target = name_by_id.get(
                str(payload["target_id"]), str(payload["target_id"])
            )
            lines.append(
                f"{attacker} landed a CRITICAL hit on {target} "
                f"({payload['total']} vs AC {payload['target_ac']})."
            )
        elif envelope.event_type == "character_defeated":
            name = name_by_id.get(
                str(payload["character_id"]), str(payload["character_id"])
            )
            lines.append(f"{name} is defeated.")
        elif envelope.event_type == "combat_ended":
            lines.append(
                f"Combat ended in round {payload['round_number']}: "
                f"{payload['winner_side']} wins."
            )
    return lines


class InvalidGmResponseError(ValueError):
    """A structured GM response carries no usable content (spec D8)."""


GM_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "narration": {"type": "string"},
        "npc_reply": {"type": "string"},
        "addressed_to": {"type": "string"},
    },
    "required": ["narration"],
    "additionalProperties": False,
}


def map_gm_response(
    data: Mapping[str, Any], profile: GmProfile, view: GameView
) -> tuple[str | None, str | None, str | None]:
    """Validate and cosmetically clean a GM response (spec D8).

    Returns (narration, npc_reply, addressed_to). Cosmetic problems collapse
    or truncate; only a response with no content at all raises. Optional
    fields are plain strings the model omits when silent (the shared schema
    validator supports single types only, so nulls never appear).
    """
    narration = _clean_text(data.get("narration"), profile.narration_max_chars)
    reply = _clean_text(data.get("npc_reply"), profile.reply_max_chars)
    addressed = data.get("addressed_to")
    if addressed is not None and not isinstance(addressed, str):
        raise InvalidGmResponseError("GM response addressed_to must be a string")
    if addressed is not None:
        living = {member.name for member in view.enemies if not member.is_defeated}
        addressed = addressed if addressed in living else None
    if narration is None and reply is None:
        raise InvalidGmResponseError("GM response has neither narration nor npc_reply")
    return narration, reply, addressed


def _clean_text(raw: Any, max_chars: int) -> str | None:
    """Collapse internal whitespace and truncate; empty/None → None."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise InvalidGmResponseError("GM response text fields must be strings")
    collapsed = " ".join(raw.split())
    if not collapsed:
        return None
    return collapsed[:max_chars]


_TASK_INSTRUCTIONS: dict[str, str] = {
    "narrate_open": "Narrate the opening of the fight in at most two sentences.",
    "react_to_events": (
        "Narrate a short reaction to the notable events in at most two sentences."
    ),
    "respond_to_player": (
        "Reply as the most fitting living enemy (set npc_reply and addressed_to), "
        "then at most one short narration sentence. Omit npc_reply and addressed_to "
        "entirely when no enemy would answer."
    ),
}


def build_gm_context(
    profile: GmProfile,
    view: GameView,
    digest: list[str],
    history: tuple[GmMessage, ...],
    task: str,
) -> tuple[str, str]:
    """Assemble the GM prompt (spec D7): persona + hard rules, scene + digest + history."""
    if task not in _TASK_INSTRUCTIONS:
        raise ValueError(f"unknown GM task: {task!r}")
    system = (
        f"You are {profile.name}, the Game Master of a D&D-style skirmish.\n"
        f"Style: {profile.style}\n"
        "Hard rules:\n"
        "- Restate only what the scene roster, notable-event digest, and conversation "
        "contain; never invent dice results, damage numbers, HP, or outcomes.\n"
        "- Never propose or execute game actions; you narrate and speak for enemies only.\n"
        "- Keep it short and concrete."
    )
    user_parts = [f"Task: {task}", "Scene:", *_roster_lines(view)]
    if digest:
        user_parts.append("Notable events:")
        user_parts.extend(f"- {line}" for line in digest)
    if history:
        user_parts.append("Conversation so far:")
        user_parts.extend(
            f"- {message.speaker}: {message.text}" for message in history
        )
    user_parts.append(_TASK_INSTRUCTIONS[task])
    return system, "\n".join(user_parts)


def _roster_lines(view: GameView) -> list[str]:
    lines: list[str] = []
    for member in (*view.party, *view.enemies):
        if member.is_defeated:
            state = "defeated"
        else:
            state = f"{member.hp_current}/{member.hp_max} HP"
        lines.append(f"- {member.name} ({member.character_class or '?'}): {state}")
    return lines
