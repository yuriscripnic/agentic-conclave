"""Ruleset data errors (R2 spec §3): load-time and resolve-time."""

from __future__ import annotations


class RulesetError(ValueError):
    """Rules data is malformed or missing; the message names file and entry."""


class UnknownRuleEntry(RulesetError):
    """A ruleset was asked for an id it does not define."""

    def __init__(self, kind: str, entry_id: str) -> None:
        self.kind = kind
        self.entry_id = entry_id
        super().__init__(f"unknown {kind} id {entry_id!r} in the active ruleset")
