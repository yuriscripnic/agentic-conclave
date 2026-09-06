"""Party message board (§32 first slice): broadcast chatter, agent-layer only (§10)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartyMessage:
    """One broadcast party-chat line; never game truth (spec §3.1)."""

    actor_name: str
    text: str
    round_number: int


class PartyMessageBoard:
    """In-memory broadcast board: unbounded appends, bounded reads (spec §3.1)."""

    def __init__(self) -> None:
        self._messages: list[PartyMessage] = []

    def post(self, message: PartyMessage) -> None:
        self._messages.append(message)

    def recent(self, limit: int = 8) -> tuple[PartyMessage, ...]:
        if limit <= 0:
            return ()
        return tuple(self._messages[-limit:])
