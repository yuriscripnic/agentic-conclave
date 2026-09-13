# OpenCode Go Provider Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenCode Go (`https://opencode.ai/zen/go/v1`, model `glm-5.3-flash`) the project's default LLM provider, with agent-memory embeddings falling back to the deterministic embedder when Go is active.

**Architecture:** New `OpenCodeGoModelGateway` subclassing the existing `OpenRouterModelGateway` (both OpenAI-compatible); the base class gains class-level hooks for provider name, default base URL, and extra headers. Factory registry, `config/llm.toml`, eval CLI, `.env.example`, and README all switch to `opencode-go`. pgvector storage is untouched.

**Tech Stack:** Python 3.12, httpx (MockTransport for tests), pytest, TOML config. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-opencode-go-provider-design.md`

## Global Constraints

- Provider string everywhere user-facing: `opencode-go` (with hyphen).
- Env var: `OPENCODE_API_KEY` (user directive 2026-09-13; NOT `OPENCODE_GO_API_KEY`).
- Go base URL: `https://opencode.ai/zen/go/v1`; chat endpoint `{base}/chat/completions`.
- Model ID: `glm-5.3-flash` (no `z-ai/` prefix through Go).
- Go pricing (verified 2026-09-13): input $0.15 / output $0.50 per million tokens. GLM-5.2 upgrade path: $1.40 / $4.40.
- Embeddings: `[profiles.embedding]` stays `openrouter` / `openai/text-embedding-3-small`. When the resolved chat provider is `opencode-go`, the session factory uses `DeterministicEmbeddingGateway`.
- Python 3.12, mypy strict, ruff (E,F,I,UP,B), line length 100.
- Commands: `.venv/bin/pytest -m "not live"`, `.venv/bin/ruff check src tests`, `.venv/bin/mypy src`.
- TDD: every task writes the failing test first, sees it fail, implements, sees it pass, commits.
- Never commit credentials; secrets only via env vars.

## File Structure

```text
src/infrastructure/llm/openrouter/adapter.py   # generalized: _provider_name, _default_base_url, _default_headers hooks
src/infrastructure/llm/opencodego/__init__.py  # new package (empty docstring)
src/infrastructure/llm/opencodego/adapter.py   # OpenCodeGoModelGateway (subclass, ~60 lines)
src/infrastructure/llm/__init__.py             # registry: {"openrouter": …, "opencode-go": …}
config/llm.toml                                # default_provider + 5 chat profiles → opencode-go; pricing swap
src/session/factory.py                         # provider→env-var map; deterministic embedder for opencode-go
src/evaluation/cli.py                          # --provider gains "opencode-go"; env-var preflight map
src/evaluation/runner.py                       # _PROVIDER_MODES gains "opencode-go"
tests/infrastructure/llm/test_opencodego_adapter.py        # new: MockTransport adapter tests
tests/infrastructure/llm/test_factory.py                   # registry test for opencode-go
tests/ai/models/test_profiles.py                           # shipped-config assertions updated
tests/session/test_session_factory.py                      # env-var mapping + embedder fallback tests
tests/interfaces/test_cli.py                               # OPENCODE_API_KEY preflight tests
tests/evaluation/test_eval_cli.py                          # opencode-go preflight test
tests/integration/test_opencodego_live.py                  # new: live smoke (skipped without key)
.env.example                                   # OPENCODE_API_KEY first
README.md                                      # provider docs swap
docs/superpowers/specs/2026-09-13-opencode-go-provider-design.md  # already written & committed
```

Task order: adapter generalization + new adapter (Task 1) → factory registry (Task 2) → config + profile tests (Task 3) → session factory wiring (Task 4) → eval CLI/runner (Task 5) → CLI preflight + env + README (Task 6) → live test (Task 7) → full verification (Task 8).

---

### Task 1: Generalize the OpenRouter adapter and add `OpenCodeGoModelGateway`

**Files:**
- Modify: `src/infrastructure/llm/openrouter/adapter.py`
- Create: `src/infrastructure/llm/opencodego/__init__.py`
- Create: `src/infrastructure/llm/opencodego/adapter.py`
- Test: `tests/infrastructure/llm/test_opencodego_adapter.py`

**Interfaces:**
- Consumes: existing `OpenRouterModelGateway` (constructor `(api_key, *, base_url, client, pricing, app_url, app_title)`), `ModelRequest`, `Message`, `ModelPricing` from `ai.models.types` / `ai.models.profiles`.
- Produces: `OpenCodeGoModelGateway(api_key: str, *, base_url: str = "https://opencode.ai/zen/go/v1", client: httpx.AsyncClient | None = None, pricing: Mapping[str, ModelPricing] | None = None, session_id: str | None = None)` — subclass of `OpenRouterModelGateway`; class attributes `PROVIDER_NAME = "opencode-go"`, `DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"`. Base class gains class attributes `PROVIDER_NAME = "openrouter"`, `DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"` and method `_default_headers() -> dict[str, str]`. The base constructor signature is unchanged (no caller changes in this task). `OpenCodeGoModelGateway.embed()` raises `ModelError("OpenCode Go does not expose an embeddings endpoint")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/infrastructure/llm/test_opencodego_adapter.py`:

```python
import asyncio
import json

import httpx
import pytest

from ai.models.errors import MissingAPIKeyError, ModelError
from ai.models.profiles import ModelPricing
from ai.models.types import Message, ModelRequest
from infrastructure.llm.opencodego.adapter import OpenCodeGoModelGateway

_SUCCESS_BODY = {
    "id": "resp-1",
    "model": "glm-5.3-flash",
    "choices": [
        {
            "message": {"role": "assistant", "content": "I will strike the goblin."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}


def _request(**overrides) -> ModelRequest:
    fields = {
        "messages": (Message(role="user", content="decide"),),
        "model": "glm-5.3-flash",
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def _gateway(handler, **kwargs) -> OpenCodeGoModelGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenCodeGoModelGateway("test-key", client=client, **kwargs)


def test_generate_hits_go_endpoint_with_go_headers() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["user_agent"] = request.headers.get("User-Agent")
        captured["session"] = request.headers.get("x-opencode-session")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request(temperature=0.4)))

    assert captured["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["user_agent"] == "agentic-conclave/0.1"
    assert captured["session"]  # a stable non-empty session id exists
    assert captured["session"] == gateway.session_id
    assert captured["body"]["model"] == "glm-5.3-flash"
    assert captured["body"]["temperature"] == 0.4
    assert "HTTP-Referer" not in captured and "X-Title" not in captured

    assert response.text == "I will strike the goblin."
    assert response.invocation.provider == "opencode-go"
    assert response.invocation.status == "ok"
    assert response.invocation.operation == "generate"
    assert response.invocation.request_id


def test_generate_computes_cost_from_go_pricing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SUCCESS_BODY)

    pricing = {"glm-5.3-flash": ModelPricing(0.15, 0.50)}
    gateway = _gateway(handler, pricing=pricing)
    response = asyncio.run(gateway.generate(_request()))
    expected = 11 / 1_000_000 * 0.15 + 7 / 1_000_000 * 0.50
    assert response.invocation.estimated_cost_usd == pytest.approx(expected)


def test_session_id_is_stable_per_instance_and_explicit_override_wins() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers.get("x-opencode-session") or "")
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    asyncio.run(gateway.generate(_request()))
    asyncio.run(gateway.generate(_request()))
    assert sent[0] == sent[1] == gateway.session_id

    custom = _gateway(handler, session_id="my-session")
    asyncio.run(custom.generate(_request()))
    assert custom.session_id == "my-session"
    assert sent[-1] == "my-session"


def test_generate_structured_labels_provider_opencodego() -> None:
    body = {
        **_SUCCESS_BODY,
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"action_type": "attack"}),
                },
                "finish_reason": "stop",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    response = asyncio.run(
        gateway.generate_structured(_request(), {"type": "object"})
    )
    assert response.data == {"action_type": "attack"}
    assert response.invocation.provider == "opencode-go"


def test_embed_raises_not_supported() -> None:
    from ai.memory.types import EmbeddingRequest

    gateway = OpenCodeGoModelGateway("test-key")
    with pytest.raises(ModelError, match="embeddings"):
        asyncio.run(
            gateway.embed(EmbeddingRequest(texts=("x",), model="glm-5.3-flash"))
        )


def test_empty_api_key_rejected_at_construction() -> None:
    with pytest.raises(MissingAPIKeyError):
        OpenCodeGoModelGateway("")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/infrastructure/llm/test_opencodego_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.llm.opencodego'`

- [ ] **Step 3: Generalize the base adapter**

In `src/infrastructure/llm/openrouter/adapter.py` make these minimal edits (all existing behavior preserved):

a) Add class attributes and replace the hardcoded strings. The class becomes:

```python
class OpenRouterModelGateway:
    PROVIDER_NAME = "openrouter"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        pricing: Mapping[str, ModelPricing] | None = None,
        app_url: str | None = None,
        app_title: str | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("OpenRouter API key is empty; set OPENROUTER_API_KEY")
        self._api_key = api_key
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._client = client
        self._pricing = dict(pricing) if pricing is not None else {}
        self._app_url = app_url
        self._app_title = app_title
```

b) Replace every literal `provider="openrouter"` in `generate`, `generate_structured`, `embed`, and `_with_invocation` with `provider=self.PROVIDER_NAME`.

c) Add the header hook and use it in `_post` (replacing the current header construction):

```python
    def _default_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._app_url is not None:
            headers["HTTP-Referer"] = self._app_url
        if self._app_title is not None:
            headers["X-Title"] = self._app_title
        return headers

    async def _post(
        self, url: str, payload: dict[str, Any], timeout_seconds: float
    ) -> httpx.Response:
        headers = self._default_headers()
        timeout = httpx.Timeout(timeout_seconds)
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient() as client:
            return await client.post(url, json=payload, headers=headers, timeout=timeout)
```

- [ ] **Step 4: Verify OpenRouter tests still pass (constructor default preserved)**

Run: `.venv/bin/pytest tests/infrastructure/llm/test_openrouter_adapter.py tests/infrastructure/llm/test_openrouter_embed.py -v`
Expected: PASS (base_url default moved to class attribute; behavior identical)

- [ ] **Step 5: Create the Go adapter package**

`src/infrastructure/llm/opencodego/__init__.py`:

```python
"""OpenCode Go adapter — OpenAI-compatible subscription gateway (spec 2026-09-13)."""
```

`src/infrastructure/llm/opencodego/adapter.py`:

```python
"""OpenCode Go adapter: OpenRouterModelGateway pointed at the Go endpoint."""

import uuid
from collections.abc import Mapping

import httpx

from ai.memory.types import EmbeddingRequest, EmbeddingResponse
from ai.models.errors import MissingAPIKeyError, ModelError
from ai.models.profiles import ModelPricing
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_USER_AGENT = "agentic-conclave/0.1"


class OpenCodeGoModelGateway(OpenRouterModelGateway):
    PROVIDER_NAME = "opencode-go"
    DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        pricing: Mapping[str, ModelPricing] | None = None,
        session_id: str | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError(
                "OpenCode Go API key is empty; set OPENCODE_API_KEY"
            )
        super().__init__(
            api_key, base_url=base_url, client=client, pricing=pricing
        )
        self.session_id = session_id or uuid.uuid4().hex

    def _default_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": _USER_AGENT,
            "x-opencode-session": self.session_id,
        }

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Go exposes no /embeddings endpoint; memory embeds deterministically."""
        raise ModelError("OpenCode Go does not expose an embeddings endpoint")
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/infrastructure/llm/test_opencodego_adapter.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Lint and typecheck**

Run: `.venv/bin/ruff check src/infrastructure tests/infrastructure && .venv/bin/mypy src/infrastructure`
Expected: no errors. Fix any F401/strict-mode complaints (e.g. unused imports) before committing.

- [ ] **Step 8: Commit**

```bash
git add src/infrastructure/llm/openrouter/adapter.py src/infrastructure/llm/opencodego tests/infrastructure/llm/test_opencodego_adapter.py
git commit -m "feat(ai): add OpenCode Go model gateway adapter"
```

---

### Task 2: Register `opencode-go` in the gateway factory

**Files:**
- Modify: `src/infrastructure/llm/__init__.py`
- Test: `tests/infrastructure/llm/test_factory.py`

**Interfaces:**
- Consumes: `OpenCodeGoModelGateway` from Task 1.
- Produces: `create_gateway("opencode-go", api_key="k")` returns an `OpenCodeGoModelGateway`. Registry `_PROVIDERS` maps `"openrouter"` and `"opencode-go"` to their adapters. `create_embedding_gateway` unchanged (still OpenRouter-only, so `create_embedding_gateway("opencode-go", …)` raises `UnknownProviderError`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/infrastructure/llm/test_factory.py` (file currently has two tests; keep them):

```python
def test_factory_builds_opencodego_gateway() -> None:
    from infrastructure.llm.opencodego.adapter import OpenCodeGoModelGateway

    gateway = create_gateway("opencode-go", api_key="k")
    assert isinstance(gateway, OpenCodeGoModelGateway)


def test_factory_rejects_opencodego_as_embedding_provider() -> None:
    from ai.models.errors import UnknownProviderError

    with pytest.raises(UnknownProviderError, match="opencode-go"):
        create_embedding_gateway("opencode-go", api_key="k")
```

Also add the import near the top (after the existing `create_gateway` import):

```python
from infrastructure.llm import create_embedding_gateway, create_gateway
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway
```

(Replace the existing import line `from infrastructure.llm import create_gateway` with the two-line version above.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/infrastructure/llm/test_factory.py -v`
Expected: FAIL — `UnknownProviderError: no model gateway registered for provider 'opencode-go'` (test 3), and test 4 fails on the registry lookup message.

- [ ] **Step 3: Register the provider**

Replace `src/infrastructure/llm/__init__.py` with:

```python
"""Provider-side model gateway implementations and the provider factory (CLAUDE.md §24)."""

from collections.abc import Mapping

from ai.memory.ports import EmbeddingGateway
from ai.models.errors import UnknownProviderError
from ai.models.gateway import ModelGateway
from ai.models.profiles import ModelPricing
from infrastructure.llm.opencodego.adapter import OpenCodeGoModelGateway
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_PROVIDERS: dict[str, type[ModelGateway]] = {
    "openrouter": OpenRouterModelGateway,
    "opencode-go": OpenCodeGoModelGateway,
}

_EMBEDDING_PROVIDERS: dict[str, type[EmbeddingGateway]] = {
    "openrouter": OpenRouterModelGateway,
}


def create_gateway(
    provider: str,
    *,
    api_key: str,
    pricing: Mapping[str, ModelPricing] | None = None,
) -> ModelGateway:
    """Build the gateway registered for *provider*; fail fast on unknown names."""
    adapter_class = _PROVIDERS.get(provider)
    if adapter_class is None:
        raise UnknownProviderError(f"no model gateway registered for provider {provider!r}")
    return adapter_class(api_key, pricing=pricing)


def create_embedding_gateway(provider: str, *, api_key: str) -> EmbeddingGateway:
    """Build the embedding gateway registered for *provider* (Plan 6 carve-out)."""
    adapter_class = _EMBEDDING_PROVIDERS.get(provider)
    if adapter_class is None:
        raise UnknownProviderError(
            f"no embedding gateway registered for provider {provider!r}"
        )
    return adapter_class(api_key)
```

`create_embedding_gateway` gets its own registry (`_EMBEDDING_PROVIDERS`) so `create_embedding_gateway("opencode-go", …)` raises `UnknownProviderError` instead of constructing a chat-only gateway. `create_embedding_gateway("openrouter", …)` behavior is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/infrastructure/llm/ -v`
Expected: PASS (all adapter + factory tests, old and new)

- [ ] **Step 5: Lint, typecheck, commit**

Run: `.venv/bin/ruff check src/infrastructure tests/infrastructure && .venv/bin/mypy src/infrastructure`
Expected: clean.

```bash
git add src/infrastructure/llm/__init__.py tests/infrastructure/llm/test_factory.py
git commit -m "feat(ai): register opencode-go in the gateway factory"
```

---

### Task 3: Switch `config/llm.toml` to opencode-go and update shipped-config tests

**Files:**
- Modify: `config/llm.toml`
- Modify: `tests/ai/models/test_profiles.py`

**Interfaces:**
- Consumes: nothing (config + tests only).
- Produces: `default_provider = "opencode-go"`; chat profiles use `model = "glm-5.3-flash"`; pricing keys `glm-5.3-flash`, `glm-5.2`, `openai/text-embedding-3-small`. Later tasks (4, 5) rely on `catalog.default_provider == "opencode-go"` and `catalog.get("player").model == "glm-5.3-flash"`.

- [ ] **Step 1: Update the shipped-config tests first (they encode the new truth)**

In `tests/ai/models/test_profiles.py`, make exactly these changes:

a) `_MINIMAL_TOML` (line ~5) stays as-is — it only tests the parser against arbitrary strings; leave the `openrouter` strings inside untouched.

b) `test_shipped_config_has_six_cheap_profiles` (line ~80) becomes:

```python
def test_shipped_config_has_six_cheap_profiles() -> None:
    config = Path(__file__).parents[3] / "config" / "llm.toml"
    catalog = load_model_profiles(config)
    assert catalog.default_provider == "opencode-go"
    assert set(catalog.profiles) == {
        "gm",
        "player",
        "cheap",
        "reasoning",
        "creative",
        "embedding",
    }
    for name, profile in catalog.profiles.items():
        if name == "embedding":
            continue  # the one sanctioned carve-out (Plan 6, user decision 2026-09-06)
        assert profile.provider == "opencode-go"
        assert profile.model == "glm-5.3-flash"
    assert set(catalog.pricing) == {
        "glm-5.3-flash",
        "glm-5.2",
        "openai/text-embedding-3-small",
    }
```

c) `test_shipped_config_embedding_profile_is_the_sanctioned_carve_out` (line ~103) stays unchanged — it already asserts `openrouter` / `openai/text-embedding-3-small`, which remain true.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ai/models/test_profiles.py -v`
Expected: FAIL — `test_shipped_config_has_six_cheap_profiles` (config still says openrouter / z-ai model / z-ai pricing).

- [ ] **Step 3: Rewrite `config/llm.toml`**

Replace the whole file with:

```toml
# Model profiles for the Agentic Conclave model gateway (Plan 3).
# No secrets here: the OpenCode Go key comes from the OPENCODE_API_KEY env var.
# Until the final version, ALL chat profiles use the cheap model (user directive,
# 2026-09-04); upgrading a profile is a one-line config edit.
# Provider switch (user decision 2026-09-13): chat models are served through
# OpenCode Go (https://opencode.ai/zen/go/v1) instead of OpenRouter.
# Carve-out (explicit user decision 2026-09-06): [profiles.embedding] still uses
# openai/text-embedding-3-small via OpenRouter's embeddings endpoint, because
# OpenCode Go exposes no /embeddings endpoint. When the chat provider is
# opencode-go the session factory falls back to the deterministic embedder
# (user decision 2026-09-13), so no key is required unless --agent llm runs
# with the chat provider set to openrouter.

default_provider = "opencode-go"

[profiles.gm]
provider = "opencode-go"
model = "glm-5.3-flash"
temperature = 0.8
max_tokens = 1024

[profiles.player]
provider = "opencode-go"
model = "glm-5.3-flash"
temperature = 0.7
max_tokens = 1024

[profiles.cheap]
provider = "opencode-go"
model = "glm-5.3-flash"
temperature = 0.5
max_tokens = 512

[profiles.reasoning]
provider = "opencode-go"
model = "glm-5.3-flash"
temperature = 0.3

[profiles.creative]
provider = "opencode-go"
model = "glm-5.3-flash"
temperature = 1.0

[profiles.embedding]  # Plan 6 agent-memory embeddings (OpenAI-compatible /embeddings)
provider = "openrouter"
model = "openai/text-embedding-3-small"

[pricing."glm-5.3-flash"]  # OpenCode Go pricing, verified 2026-09-13; USD per million tokens
input_per_million_usd = 0.15
output_per_million_usd = 0.50

[pricing."glm-5.2"]  # OpenCode Go upgrade path, verified 2026-09-13
input_per_million_usd = 1.40
output_per_million_usd = 4.40

[pricing."openai/text-embedding-3-small"]  # verified 2026-09-06; USD per million tokens
input_per_million_usd = 0.02
output_per_million_usd = 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ai/models/test_profiles.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/llm.toml tests/ai/models/test_profiles.py
git commit -m "feat(config): switch chat profiles to opencode-go"
```

---

### Task 4: Session factory — env-var mapping and deterministic embedder fallback

**Files:**
- Modify: `src/session/factory.py:172-248` (`_wire_gm`, `_wire_party`)
- Test: `tests/session/test_session_factory.py`

**Interfaces:**
- Consumes: `create_gateway` registry (Task 2); `catalog.default_provider == "opencode-go"` (Task 3); `DeterministicEmbeddingGateway` from `ai.memory.fake` (already imported in factory).
- Produces: module-level `PROVIDER_API_KEY_ENV: dict[str, str] = {"opencode-go": "OPENCODE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}` and `_resolve_api_key(provider: str) -> str` raising `ValueError("OPENCODE_API_KEY is not set; export it to run with --agent llm")` (message names the exact env var for the requested provider). `_wire_gm`/`_wire_party` call it instead of reading `OPENROUTER_API_KEY` directly. `_wire_party` uses the deterministic embedder whenever the resolved chat provider is `opencode-go` (Go has no /embeddings endpoint, spec Decision 4).

- [ ] **Step 1: Write the failing tests**

Append to `tests/session/test_session_factory.py`:

```python
def test_agent_llm_requires_opencode_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENCODE_API_KEY"):
        build_session(SessionConfig(seed=42, agent_mode="llm"))


def test_gm_llm_requires_opencode_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENCODE_API_KEY"):
        build_session(SessionConfig(seed=42, gm_mode="llm"))


def test_agent_llm_opencodego_uses_deterministic_embedder(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    session = build_session(SessionConfig(seed=42, agent_mode="llm"))
    turn_service = session.turn_service
    assert turn_service is not None
    memory = turn_service._memory  # composition-root wiring detail; acceptable in tests
    from ai.memory.fake import DeterministicEmbeddingGateway

    assert isinstance(memory._gateway, DeterministicEmbeddingGateway)


def test_agent_llm_openrouter_uses_real_embedding_gateway(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")  # chat key unused in this path
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    session = build_session(
        SessionConfig(seed=42, agent_mode="llm", provider="openrouter")
    )
    turn_service = session.turn_service
    assert turn_service is not None
    memory = turn_service._memory
    from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

    assert isinstance(memory._gateway, OpenRouterModelGateway)
```

Note for the implementer: `MemoryService` stores its embedder as `self._gateway` (`src/application/memory/memory_service.py:31`), which both tests assert against. Do not change `MemoryService`'s public surface for tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/session/test_session_factory.py -v`
Expected: FAIL — first two tests fail with `ValueError` mentioning `OPENROUTER_API_KEY` (match fails); the two embedder tests fail because the chat gateway is still OpenRouter's.

- [ ] **Step 3: Implement the mapping and fallback in `src/session/factory.py`**

a) Add module-level constants and helper just above `_gm_decision` (~line 118):

```python
PROVIDER_API_KEY_ENV = {
    "opencode-go": "OPENCODE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _resolve_api_key(provider: str) -> str:
    """Map a provider name to its env-var key; fail with the variable's name."""
    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var is None:
        raise ValueError(
            f"unknown provider {provider!r}; known providers: "
            f"{', '.join(sorted(PROVIDER_API_KEY_ENV))}"
        )
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"{env_var} is not set; export it to run with llm mode")
    return api_key
```

b) In `_wire_gm` (lines ~179-190), replace:

```python
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is not set; export it to run with --gm llm"
                )
            gateway = create_gateway(
                config.provider or model_catalog.default_provider, api_key=api_key
            )
```

with:

```python
            provider = config.provider or model_catalog.default_provider
            gateway = create_gateway(provider, api_key=_resolve_api_key(provider))
```

c) In `_wire_party` (lines ~209-221), apply the same replacement to the agent path (`--agent llm` message context is preserved by the helper's generic message; if you want mode-specific messages, pass a `purpose` parameter: `_resolve_api_key(provider, purpose="--agent llm")` and format `f"{env_var} is not set; export it to run with {purpose}"`. Do this — it preserves today's message quality.)

Final helper shape:

```python
def _resolve_api_key(provider: str, purpose: str) -> str:
    """Map a provider name to its env-var key; fail with the variable's name."""
    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var is None:
        raise ValueError(
            f"unknown provider {provider!r}; known providers: "
            f"{', '.join(sorted(PROVIDER_API_KEY_ENV))}"
        )
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"{env_var} is not set; export it to run with {purpose}")
    return api_key
```

Call sites: `api_key = _resolve_api_key(provider, "--gm llm")` and `api_key = _resolve_api_key(provider, "--agent llm")` respectively.

d) In `_wire_party`, change the embedder selection (lines ~237-242) from key-presence-based to provider-based:

```python
    embedding_profile = model_catalog.get("embedding")
    embedder: EmbeddingGateway
    chat_provider = config.provider or model_catalog.default_provider
    if chat_provider == "opencode-go":
        # OpenCode Go exposes no /embeddings endpoint (spec 2026-09-13,
        # Decision 4): memory embeds with the deterministic gateway.
        embedder = DeterministicEmbeddingGateway()
    elif api_key is not None:
        embedder = create_embedding_gateway(embedding_profile.provider, api_key=api_key)
    else:
        embedder = DeterministicEmbeddingGateway()
```

(The `api_key` variable is still assigned in the llm branch above; when `config.gateway` was injected, `api_key` stays `None` and the deterministic embedder is used — same as today's behavior.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/session/test_session_factory.py -v`
Expected: PASS (all tests including the pre-existing six)

- [ ] **Step 5: Run the CLI preflight tests that also touch this code path**

Run: `.venv/bin/pytest tests/interfaces/test_cli.py -v -k "requires_api_key"`
Expected: these will FAIL (they assert `OPENROUTER_API_KEY` in output) — that's expected; they are updated in Task 6. Note the failures and continue.

- [ ] **Step 6: Lint, typecheck, commit**

Run: `.venv/bin/ruff check src/session tests/session && .venv/bin/mypy src/session`
Expected: clean.

```bash
git add src/session/factory.py tests/session/test_session_factory.py
git commit -m "feat(session): resolve provider API keys and fall back to deterministic embedder for opencode-go"
```

---

### Task 5: Evaluation CLI and runner accept `opencode-go`

**Files:**
- Modify: `src/evaluation/cli.py:63-77`
- Modify: `src/evaluation/runner.py:37-60`
- Test: `tests/evaluation/test_eval_cli.py`

**Interfaces:**
- Consumes: `PROVIDER_API_KEY_ENV` from Task 4 (import from `session.factory`).
- Produces: `conclave-eval --provider opencode-go` works; `_PROVIDER_MODES` gains `"opencode-go": ("llm", "llm")`; preflight checks `PROVIDER_API_KEY_ENV.get(args.provider)` when the provider is not `fake` and exits 2 with the env-var name if unset. `run_scenario` passes `provider=provider if provider in ("openrouter", "opencode-go") else None` into `SessionConfig`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/evaluation/test_eval_cli.py` (it already imports `main` and defines `_console()`; add `from pytest import MonkeyPatch` to the imports):

```python
def test_eval_cli_opencodego_without_api_key_exits_2(
    monkeypatch: MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    console, buffer = _console()

    code = main(
        ["--provider", "opencode-go", "--out-dir", str(tmp_path)], console=console
    )

    assert code == 2
    assert "OPENCODE_API_KEY" in buffer.getvalue()


def test_eval_cli_opencodego_provider_choice_is_recognized(
    monkeypatch: MonkeyPatch, tmp_path
) -> None:
    """Unknown-scenario error (exit 2) proves --provider parsed; preflight ran first."""
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    console, buffer = _console()

    code = main(
        [
            "--provider",
            "opencode-go",
            "--scenario",
            "dragon-hoard",
            "--out-dir",
            str(tmp_path),
        ],
        console=console,
    )

    assert code == 2
    assert "unknown scenario" in buffer.getvalue()

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/evaluation/test_eval_cli.py -v`
Expected: FAIL — first test: `--provider opencode-go` is rejected by argparse (`invalid choice`), producing exit code 2 but without `OPENCODE_API_KEY` in output.

- [ ] **Step 3: Update the eval CLI**

In `src/evaluation/cli.py`, change lines 63 and 73-77:

```python
    parser.add_argument(
        "--provider", choices=("fake", "openrouter", "opencode-go"), default="fake"
    )
```

and the preflight (import `PROVIDER_API_KEY_ENV` from `session.factory` at the top, after the existing imports):

```python
    env_var = PROVIDER_API_KEY_ENV.get(args.provider) if args.provider != "fake" else None
    if env_var and not os.environ.get(env_var):
        console.print(
            f"[red]{env_var} is not set; export it to run live evaluation[/red]"
        )
        return 2
```

- [ ] **Step 4: Update the runner**

In `src/evaluation/runner.py`:

```python
_PROVIDER_MODES = {
    "fake": ("fake", "fake"),
    "openrouter": ("llm", "llm"),
    "opencode-go": ("llm", "llm"),
}
_LLM_PROVIDERS = ("openrouter", "opencode-go")
```

and in `run_scenario` (line ~59):

```python
        provider=provider if provider in _LLM_PROVIDERS else None,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/evaluation/ -v`
Expected: PASS (all existing eval tests + the two new ones)

- [ ] **Step 6: Lint, typecheck, commit**

Run: `.venv/bin/ruff check src/evaluation tests/evaluation && .venv/bin/mypy src/evaluation`
Expected: clean.

```bash
git add src/evaluation/cli.py src/evaluation/runner.py tests/evaluation/test_eval_cli.py
git commit -m "feat(evaluation): support opencode-go as a live evaluation provider"
```

---

### Task 6: CLI preflight tests, `.env.example`, README

**Files:**
- Modify: `tests/interfaces/test_cli.py:112-118, 186-191`
- Modify: `.env.example`
- Modify: `README.md:40-46, 55-60, 84-91, 109-112, 142`

**Interfaces:**
- Consumes: the factory's new error message (`OPENCODE_API_KEY is not set; export it to run with --agent llm`) from Task 4.
- Produces: documentation and tests that name `OPENCODE_API_KEY` as the live-chat key.

- [ ] **Step 1: Update the two CLI preflight tests (they currently fail from Task 4)**

In `tests/interfaces/test_cli.py`:

a) `test_main_agent_llm_requires_api_key` (line 112) becomes:

```python
def test_main_agent_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=["--agent", "llm"], console=console, input_fn=_scripted())
    assert code == 2
    assert "OPENCODE_API_KEY" in buffer.getvalue()
```

b) `test_main_gm_llm_requires_api_key` (line 186) becomes:

```python
def test_main_gm_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    console, buffer = _console()
    code = main(argv=["--gm", "llm"], console=console, input_fn=_scripted("/quit"))
    assert code == 2
    assert "OPENCODE_API_KEY" in buffer.getvalue()
```

- [ ] **Step 2: Run to verify they pass**

Run: `.venv/bin/pytest tests/interfaces/test_cli.py -v`
Expected: PASS (all CLI tests)

- [ ] **Step 3: Update `.env.example`**

Replace its first variable block so the file reads:

```
# Copy to .env and fill in. .env is gitignored; never commit real credentials.
OPENCODE_API_KEY=

# Optional: OpenRouter key for agent-memory embeddings when --agent llm runs
# with the chat provider set to openrouter (config/llm.toml [profiles.embedding]).
OPENROUTER_API_KEY=

# PostgreSQL connection for --db postgres (Plan 2 persistence).
# Example: postgresql://conclave:secret@localhost:5432/conclave
DATABASE_URL=
```

- [ ] **Step 4: Update README**

a) "Model gateway" section (lines ~40-46): replace the OpenRouter sentence and export block with:

```markdown
LLM access goes through a provider-agnostic `ModelGateway` (`src/ai/models/`).
Tests and offline runs use the deterministic `FakeModelGateway`; live calls use
the OpenCode Go adapter behind `OPENCODE_API_KEY`:

```bash
export OPENCODE_API_KEY=...
```
```

b) "AI party" export block (lines ~55-60): `export OPENCODE_API_KEY=sk-or-...` → `export OPENCODE_API_KEY=...`

c) Memory bullet (lines ~87-88): replace

```
- `--agent llm` embeds with `openai/text-embedding-3-small` through OpenRouter
  (the one sanctioned carve-out from the cheap-chat-model directive).
```

with

```
- `--agent llm` embeds with the deterministic stdlib embedder when the chat
  provider is `opencode-go` (Go exposes no /embeddings endpoint); with
  `--provider openrouter` it uses `openai/text-embedding-3-small` through
  OpenRouter (the sanctioned carve-out, Plan 6).
```

d) "Game Master" section real-models block (lines ~109-111): replace `export OPENROUTER_API_KEY=...` with `export OPENCODE_API_KEY=...` and the comment `# Real models via OpenRouter` with `# Real models via OpenCode Go`.

e) Evaluation block (line 142): replace

```
OPENROUTER_API_KEY=... .venv/bin/conclave-eval --provider openrouter   # live comparison
```

with

```
OPENCODE_API_KEY=... .venv/bin/conclave-eval --provider opencode-go   # live comparison
```

- [ ] **Step 5: Verify no stale key references remain**

Run: `grep -rn "OPENROUTER_API_KEY" README.md .env.example`
Expected: only the optional-embeddings mentions (README embedding bullet stays generic; `.env.example` keeps its documented optional block). No bare "export OPENROUTER_API_KEY" instructions remain.

Run: `grep -rn "sk-or" README.md`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add tests/interfaces/test_cli.py .env.example README.md
git commit -m "docs: switch live-provider docs and CLI preflight tests to OPENCODE_API_KEY"
```

---

### Task 7: Live integration smoke test for opencode-go

**Files:**
- Create: `tests/integration/test_opencodego_live.py`

**Interfaces:**
- Consumes: `create_gateway("opencode-go", …)` (Task 2), `glm-5.3-flash` model ID (Task 3).
- Produces: a `@pytest.mark.live` test, skipped without `OPENCODE_API_KEY` (CLAUDE.md §46), mirroring `tests/integration/test_openrouter_live.py`.

- [ ] **Step 1: Write the test**

Create `tests/integration/test_opencodego_live.py`:

```python
import asyncio
import os

import pytest

from ai.models.types import Message, ModelRequest
from infrastructure.llm import create_gateway

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("OPENCODE_API_KEY"),
        reason="OPENCODE_API_KEY not set; live provider test skipped (CLAUDE.md §46)",
    ),
]


def test_opencodego_live_generate() -> None:
    gateway = create_gateway("opencode-go", api_key=os.environ["OPENCODE_API_KEY"])
    request = ModelRequest(
        messages=(Message(role="user", content="Reply with exactly: ok"),),
        model="glm-5.3-flash",
        temperature=0.0,
        max_tokens=100,
        timeout_seconds=30.0,
    )
    response = asyncio.run(gateway.generate(request))
    assert response.text
    assert response.invocation.provider == "opencode-go"
    assert response.invocation.status == "ok"
    assert response.usage.total_tokens > 0
```

- [ ] **Step 2: Verify it is skipped in the default suite**

Run: `.venv/bin/pytest tests/integration/test_opencodego_live.py -v`
Expected: 1 skipped (`OPENCODE_API_KEY not set`) — unless you have the key exported, in which case it runs and must PASS; report which happened.

- [ ] **Step 3: Verify the live marker keeps it out of the default run**

Run: `.venv/bin/pytest tests/integration -m "not live" -v`
Expected: `test_opencodego_live_generate` not collected (deselected by `-m "not live"`).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_opencodego_live.py
git commit -m "test(ai): add live OpenCode Go smoke test (skipped without OPENCODE_API_KEY)"
```

---

### Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Full test suite (non-live)**

Run: `.venv/bin/pytest -m "not live"`
Expected: all PASS, 0 failures.

- [ ] **Step 2: Lint and typecheck over everything**

Run: `.venv/bin/ruff check src tests && .venv/bin/mypy src`
Expected: clean.

- [ ] **Step 3: Offline end-to-end sanity (no network, no key needed)**

Run: `.venv/bin/python -m interfaces.cli.app --agent fake --seed 42 < /dev/null 2>&1 | tail -5`
Expected: the seeded fight renders and ends with `The adventure has ended. Thanks for playing!` (exit 0). This proves the config switch didn't disturb offline wiring (fake gateways ignore llm.toml provider values but the config must still parse).

Also: `.venv/bin/conclave-eval --scenario goblin-skirmish`
Expected: `wrote eval-results/goblin-skirmish-*.json` and `status: ok` in the JSON.

- [ ] **Step 4: Spec-compliance spot checks**

Run: `grep -n "default_provider" config/llm.toml`
Expected: `default_provider = "opencode-go"`.

Run: `grep -c "z-ai/" config/llm.toml`
Expected: `0`.

Run: `grep -n "OPENCODE_GO_API_KEY" -r src tests config README.md .env.example`
Expected: no output (the env var is `OPENCODE_API_KEY` everywhere — user directive 2026-09-13).

- [ ] **Step 5: Report**

Summarize: what changed, test counts before/after, and that `OPENCODE_API_KEY` is the only key needed for `--agent llm` / `--gm llm` / `conclave-eval --provider opencode-go` (embeddings ride the deterministic embedder per spec Decision 4).
