"""Session composition root shared by the CLI, evaluation, and future adapters (§63)."""

from session.factory import (
    CONFIG_DIR,
    GameSession,
    SessionConfig,
    build_service,
    build_session,
    open_session,
)
from session.play import (
    InputOutcome,
    PendingTurn,
    advance,
    apply_input,
    parse_input,
)

__all__ = [
    "CONFIG_DIR",
    "GameSession",
    "InputOutcome",
    "PendingTurn",
    "SessionConfig",
    "advance",
    "apply_input",
    "build_service",
    "build_session",
    "open_session",
    "parse_input",
]