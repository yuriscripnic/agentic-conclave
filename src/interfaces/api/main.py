"""uvicorn entry point for the Agentic Conclave web API."""
import os

import uvicorn

from interfaces.api.app import create_app


def main() -> None:
    app = create_app(
        agent_mode=os.environ.get("CONCLAVE_AGENT_MODE", "llm"),
        gm_mode=os.environ.get("CONCLAVE_GM_MODE", "off"),
    )
    uvicorn.run(
        app,
        host=os.environ.get("CONCLAVE_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("CONCLAVE_API_PORT", "8000")),
        workers=1,  # combat/dice/message state is per-process (contract §6)
    )


if __name__ == "__main__":
    main()
