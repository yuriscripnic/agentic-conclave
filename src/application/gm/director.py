"""GM director: notable-event digest, prompts, response mapping, hook service.

The GM proposes nothing that mutates game state (spec D1/D2): it observes
views and events and produces narration. All game authority stays in the
domain/rules engine (CLAUDE.md §1, §10).
"""

from __future__ import annotations

from application.views import TurnReport
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
