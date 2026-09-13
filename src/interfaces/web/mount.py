"""Static web UI mount (Phase 20).

Serves static assets and shell pages only. The UI consumes the Phase 19 API
contract (`docs/architecture/domain-model-and-api.md`) read-only plus the two
POST routes (`/actions`, `/input`) from the browser; this module adds no game
endpoints (CLAUDE.md §63, §40).
"""
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"


def mount_web(app: FastAPI) -> FastAPI:
    """Mount the static UI on ``app``: /assets, GET /, GET /games/{game_id}.

    ``GET /games/{game_id}`` accepts any id — the page is a pure shell; an
    unknown id fails visibly on the first poll to the API.
    """
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="web_static")
    index = _serve(STATIC_DIR / "index.html")
    game_shell = _serve(STATIC_DIR / "game.html")

    app.get("/")(index)
    app.get("/games/{game_id}")(game_shell)
    return app


def _serve(path: Path) -> Callable[[], FileResponse]:
    def handler() -> FileResponse:
        return FileResponse(path, media_type="text/html")

    return handler
