"""GM conversation board (spec §3.2): in-RAM history of player/GM/NPC lines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GmMessage:
    """One conversation line; presentation history, never game truth (§10)."""

    speaker: str  # "player" | "gm" | an NPC/enemy name
    text: str


class GmConversation:
    """Unbounded appends, bounded reads (mirrors PartyMessageBoard)."""

    def __init__(self) -> None:
        self._messages: list[GmMessage] = []

    def append(self, message: GmMessage) -> None:
        self._messages.append(message)

    def recent(self, limit: int) -> tuple[GmMessage, ...]:
        if limit <= 0:
            return ()
        return tuple(self._messages[-limit:])
