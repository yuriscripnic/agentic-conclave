"""Per-process session registry and idempotency cache for the web API.

Combat state (dice, collectors) already lives inside GameService per process;
the registry follows that model (contract §6).
"""
import threading

from session.factory import GameSession, SessionConfig, build_session


class SessionRegistry:
    """Maps game_id → GameSession for this API process."""

    def __init__(self, *, agent_mode: str, gm_mode: str) -> None:
        self._agent_mode = agent_mode
        self._gm_mode = gm_mode
        self._sessions: dict[str, GameSession] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def build(self, config: SessionConfig) -> str:
        session = build_session(config)
        game_id = str(session.game_id)
        with self._global_lock:
            self._sessions[game_id] = session
            self._locks[game_id] = threading.Lock()
        return game_id

    def get(self, game_id: str) -> GameSession:
        try:
            return self._sessions[game_id]
        except KeyError:
            raise KeyError(game_id) from None

    def __contains__(self, game_id: object) -> bool:
        return game_id in self._sessions

    def lock_for(self, game_id: str) -> threading.Lock:
        return self._locks[game_id]


class IdempotencyStore:
    """In-process dedup for state-changing routes, scoped per logical operation."""

    def __init__(self) -> None:
        self._responses: dict[tuple[str, str], object] = {}

    def response_or(self, key: str, scope: str) -> object | None:
        return self._responses.get((key, scope))

    def remember(self, key: str, scope: str, response: object) -> None:
        if key:
            self._responses[(key, scope)] = response
