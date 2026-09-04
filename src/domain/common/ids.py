"""Strongly typed identifiers for domain entities (CLAUDE.md §61)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self
from uuid import uuid4


@dataclass(frozen=True)
class EntityId:
    """Base type for strongly typed identifiers."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("id value must be a non-empty string")

    @classmethod
    def generate(cls) -> Self:
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


class CampaignId(EntityId):
    pass


class GameId(EntityId):
    pass


class CharacterId(EntityId):
    pass


class AgentId(EntityId):
    pass


class LocationId(EntityId):
    pass


class QuestId(EntityId):
    pass


class EventId(EntityId):
    pass
