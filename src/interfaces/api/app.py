"""HTTP adapter over the session/application layer (Phase 19)."""
from fastapi import FastAPI

from session.factory import SessionConfig


def create_app(*, agent_mode: str = "llm", gm_mode: str = "off") -> FastAPI:
    """Compose the API; modes come from the caller (CLI/env config, tests pass `fake`)."""
    app = FastAPI(title="Agentic Conclave API", version="0.1.0")
    app.state.agent_mode = agent_mode
    app.state.gm_mode = gm_mode
    app.state.config_factory = SessionConfig

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
