"""Explicit domain errors (CLAUDE.md §49). Expected failures are never bare Exception."""


class DomainError(Exception):
    """Base class for all expected domain failures."""


class ValidationError(DomainError):
    """A value or state is invalid."""


class CharacterNotFoundError(DomainError):
    pass


class GameNotFoundError(DomainError):
    pass


class InvalidActionError(DomainError):
    pass


class NotYourTurnError(DomainError):
    pass


class ActionNotAvailableError(DomainError):
    pass


class CombatNotActiveError(DomainError):
    pass


class InsufficientResourceError(DomainError):
    pass


class GameNotRunningError(DomainError):
    pass


class AgentDecisionFailedError(DomainError):
    pass


class ConcurrentGameModification(DomainError):
    """A save lost the optimistic-lock race: the game was modified elsewhere."""


class PersistenceError(DomainError):
    """A storage failure occurred below the repository boundary."""
