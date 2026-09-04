"""Event primitives: past-tense, immutable records of what happened (CLAUDE.md §11, §12)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from domain.common.ids import EntityId

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _snake_case(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _jsonable(value: object) -> object:
    if isinstance(value, EntityId):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


class GameEvent(Protocol):
    @property
    def event_type(self) -> str: ...

    def to_payload(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class BaseEvent:
    """Base for all domain events; subclass with frozen dataclass fields only."""

    @property
    def event_type(self) -> str:
        return _snake_case(type(self).__name__)

    def to_payload(self) -> dict[str, object]:
        # Iterate the instance dict (not asdict) so nested EntityId dataclasses
        # are still live objects when _jsonable serializes them.
        return {key: _jsonable(value) for key, value in vars(self).items()}
