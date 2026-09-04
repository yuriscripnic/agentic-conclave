import pytest

from domain.common.errors import (
    AgentDecisionFailedError,
    CombatNotActiveError,
    DomainError,
    GameNotFoundError,
    InsufficientResourceError,
    ValidationError,
)


def test_all_domain_errors_inherit_from_domain_error() -> None:
    errors = [
        ValidationError,
        GameNotFoundError,
        InsufficientResourceError,
        CombatNotActiveError,
        AgentDecisionFailedError,
    ]
    for error in errors:
        assert issubclass(error, DomainError)


def test_domain_error_is_catchable_as_exception_with_message() -> None:
    with pytest.raises(DomainError, match="no such game"):
        raise GameNotFoundError("no such game")


def test_persistence_errors_inherit_from_domain_error() -> None:
    from domain.common.errors import ConcurrentGameModification, PersistenceError

    assert issubclass(ConcurrentGameModification, DomainError)
    assert issubclass(PersistenceError, DomainError)
