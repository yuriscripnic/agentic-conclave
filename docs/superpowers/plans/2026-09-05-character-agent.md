# Character Agent (Plan 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An AI-controlled party member (Brix) decides her attacks through the model gateway — observe → prompt → structured LLM decision → validated `AttackProposal` → deterministic engine — with bounded retries and a deterministic fallback, offline by default.

**Architecture:** Split per spec decision 3: `src/ai/agents/` is a game-free decision runtime (message assembly, gateway bridging via `asyncio.run`, transport-retry policy, agent error taxonomy); `src/application/agents/` is the game-aware agent (perception from `GameView`, prompts, JSON→proposal mapping, decision-attempt loop, fallback, turn reporting). The CLI composes everything behind `--agent off|llm|fake`. Zero changes to `src/domain/` — the agent is just another caller of `GameService.submit_action`.

**Tech Stack:** Python 3.12 stdlib (`asyncio` bridging, `tomllib`, `dataclasses`, `ast`), the existing `ai.models` gateway stack from Plan 3, pytest / mypy strict / ruff.

**Spec:** `docs/superpowers/specs/2026-09-05-character-agent-design.md` — the binding authority; this plan argues from it. Where plan text and spec conflict, the spec wins (record the conflict in the execution ledger).

## Global Constraints

- `src/domain/` is untouched: `git log master..HEAD -- src/domain` must be empty for the whole branch.
- No new runtime dependencies — stdlib only (`tomllib`, `asyncio`, `ast`); gateway + httpx already exist from Plan 3.
- Provider names (`openrouter`, model ids) appear only under `src/infrastructure/llm/` and as values in `config/*.toml`.
- `config/llm.toml` is NOT modified; all model profiles remain `z-ai/glm-5.3-flash` (standing user directive).
- Secrets from environment only (`OPENROUTER_API_KEY`, `DATABASE_URL`); never committed, never logged, never echoed.
- No private chain-of-thought requested, displayed, or persisted (CLAUDE.md §33) — only the explicit `public_message`.
- Every task boundary: `.venv/bin/python -m pytest -q` green offline, `.venv/bin/python -m ruff check src tests` clean, `.venv/bin/python -m mypy` clean.
- Full-suite runs execute the opt-in live OpenRouter smoke test when `OPENROUTER_API_KEY` is set; a transient live failure there is provider jitter — rerun once before investigating.
- Conventional commits scoped by layer, each ending `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- Tests import top-level (`ai.*`, `application.*`, `domain.*`, `infrastructure.*`) — pytest `pythonpath = ["src"]`; no pytest-asyncio (use `asyncio.run`); no `__init__.py` in test directories.
- Tests never require `OPENROUTER_API_KEY` or `DATABASE_URL`; `monkeypatch.delenv(..., raising=False)` them when the behavior under test touches them.
- `ModelError` constructors take a required message: write `ModelTimeoutError("boom")`, never `ModelTimeoutError()`.
- `AgentRuntime.__init__` realizes the spec's `retry_policy: RetryPolicy = RetryPolicy()` default as `retry_policy: RetryPolicy | None = None` with coalescing (identical behavior; avoids a shared frozen-dataclass default instance).
- Baseline before Task 1: full suite green on `master` — **221 offline tests + 1 live smoke test** (the live test passes when `OPENROUTER_API_KEY` is set, skips otherwise). Gate expectations below are **offline test counts**; a full-suite run shows `N passed, 1 skipped` without the key or `N+1 passed` with it.

---

### Task 1: `src/ai/agents/` — error taxonomy + transport retry policy

**Files:**
- Create: `src/ai/agents/__init__.py`
- Create: `src/ai/agents/errors.py`
- Create: `src/ai/agents/retry.py`
- Test: `tests/ai/agents/test_retry.py`

**Interfaces:**
- Consumes: `ai.models.errors` (`ModelError`, `ModelTimeoutError`, `ModelUnavailableError`, `ModelRateLimitedError`, `ModelInvalidResponseError`, `ModelRequestError`, `MissingAPIKeyError`, `UnsupportedSchemaError`); `ai.models.types.LLMInvocation`.
- Produces: `AgentRuntimeError(message, *, attempts: int, last_invocation: LLMInvocation | None = None)` (Exception with `.attempts`, `.last_invocation`); `AgentRuntimeMisconfiguredError(AgentRuntimeError)`; `RETRYABLE_MODEL_ERRORS: tuple[type[ModelError], ...]` = (Timeout, Unavailable, RateLimited, InvalidResponse); `is_retryable(exc: BaseException) -> bool`; `RetryPolicy(max_attempts: int = 3, backoff_seconds: float = 0.0, sleep: Callable[[float], None] = time.sleep)` validating `max_attempts >= 1`, `backoff_seconds >= 0`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ai/agents/test_retry.py`:

```python
"""Retry classification and policy tests (ai.agents)."""

import pytest

from ai.agents.retry import RETRYABLE_MODEL_ERRORS, RetryPolicy, is_retryable
from ai.models.errors import (
    MissingAPIKeyError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    UnsupportedSchemaError,
)


def test_retryable_tuple_is_exactly_the_transient_failures() -> None:
    assert set(RETRYABLE_MODEL_ERRORS) == {
        ModelTimeoutError,
        ModelUnavailableError,
        ModelRateLimitedError,
        ModelInvalidResponseError,
    }


@pytest.mark.parametrize(
    "error",
    [
        ModelTimeoutError("boom"),
        ModelUnavailableError("boom"),
        ModelRateLimitedError("boom"),
        ModelInvalidResponseError("boom"),
    ],
)
def test_is_retryable_true_for_transient_errors(error: Exception) -> None:
    assert is_retryable(error) is True


@pytest.mark.parametrize(
    "error",
    [
        ModelRequestError("bad request"),
        MissingAPIKeyError("no key"),
        UnsupportedSchemaError("bad schema"),
        ValueError("unrelated"),
    ],
)
def test_is_retryable_false_for_non_retryable_errors(error: Exception) -> None:
    assert is_retryable(error) is False


def test_policy_defaults() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.backoff_seconds == 0.0


def test_policy_custom_sleep_is_retained() -> None:
    sleeps: list[float] = []

    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    policy = RetryPolicy(max_attempts=2, backoff_seconds=0.5, sleep=_sleep)
    policy.sleep(0.5)
    assert sleeps == [0.5]


def test_policy_rejects_zero_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_policy_rejects_negative_backoff() -> None:
    with pytest.raises(ValueError, match="backoff_seconds"):
        RetryPolicy(backoff_seconds=-0.1)
```

(13 test functions after parametrize expansion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/agents/test_retry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai.agents'`

- [ ] **Step 3: Implement**

`src/ai/agents/__init__.py`:

```python
"""Game-free agent runtime over the model gateway (no domain/game imports)."""
```

`src/ai/agents/errors.py`:

```python
"""Agent-layer error taxonomy (the AI layer does not reuse domain errors)."""

from __future__ import annotations

from ai.models.types import LLMInvocation


class AgentRuntimeError(Exception):
    """A bounded decision attempt exhausted its retry budget."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_invocation: LLMInvocation | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_invocation = last_invocation


class AgentRuntimeMisconfiguredError(AgentRuntimeError):
    """Non-retryable model/config failure; retrying an identical request cannot help."""
```

`src/ai/agents/retry.py`:

```python
"""Transport-retry policy for agent decisions (keyed off exception types)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ai.models.errors import (
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelTimeoutError,
    ModelUnavailableError,
)

RETRYABLE_MODEL_ERRORS: tuple[type[ModelError], ...] = (
    ModelTimeoutError,
    ModelUnavailableError,
    ModelRateLimitedError,
    ModelInvalidResponseError,
)


def is_retryable(exc: BaseException) -> bool:
    """True exactly for the transient failure types in RETRYABLE_MODEL_ERRORS."""
    return isinstance(exc, RETRYABLE_MODEL_ERRORS)


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry budget for one decision request (same request re-sent)."""

    max_attempts: int = 3
    backoff_seconds: float = 0.0
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/agents/test_retry.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/ai/agents tests/ai/agents
git commit -m "feat(ai): add agent-layer error taxonomy and transport retry policy

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `AgentRuntime` — synchronous decision loop over the gateway

**Files:**
- Create: `src/ai/agents/runtime.py`
- Test: `tests/ai/agents/test_runtime.py`

**Interfaces:**
- Consumes: Task 1's `AgentRuntimeError` / `AgentRuntimeMisconfiguredError` / `RetryPolicy` / `is_retryable`; `ai.models.gateway.ModelGateway` (Protocol with `async generate(request)`, `async generate_structured(request, schema)`); `ai.models.profiles.ModelProfile` (`.to_request(messages) -> ModelRequest` carrying model/temperature/max_tokens); `ai.models.types.{Message, ModelRequest, ModelResponse, StructuredModelResponse, LLMInvocation}`.
- Produces: `AgentRuntime(gateway: ModelGateway, retry_policy: RetryPolicy | None = None)` with `decide_structured(*, profile: ModelProfile, system: str, user: str, schema: Mapping[str, Any]) -> StructuredModelResponse`. Retryable `ModelError` → sleep backoff → retry (≤ `max_attempts`); non-retryable `ModelError` → `AgentRuntimeMisconfiguredError` (chained, `.last_invocation` set); budget exhausted → `AgentRuntimeError(attempts=max_attempts, last_invocation=...)`. **`AgentRuntimeMisconfiguredError` subclasses `AgentRuntimeError` — later tasks' `except` order must check it first.**

- [ ] **Step 1: Write the failing tests**

Create `tests/ai/agents/test_runtime.py`:

```python
"""AgentRuntime decision-loop tests."""

from collections.abc import Mapping
from typing import Any

import pytest

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelRequestError, ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile
from ai.models.types import Message, ModelRequest, ModelResponse, StructuredModelResponse

_PROFILE = ModelProfile(
    name="player",
    provider="fake",
    model="test-model",
    temperature=0.1,
    max_tokens=64,
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
_DECISION: dict[str, Any] = {"answer": "ok"}
_SYSTEM = "system prompt"
_USER = "user prompt"


def _policy(sleeps: list[float], max_attempts: int = 3) -> RetryPolicy:
    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return RetryPolicy(max_attempts=max_attempts, backoff_seconds=0.25, sleep=_sleep)


def test_success_on_first_attempt() -> None:
    fake = FakeModelGateway()
    fake.enqueue_structured(dict(_DECISION))
    runtime = AgentRuntime(fake)

    response = runtime.decide_structured(
        profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA
    )

    assert response.data == _DECISION
    assert len(fake.invocations) == 1


def test_retries_transient_error_then_succeeds() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    fake.enqueue_structured(dict(_DECISION))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps))

    response = runtime.decide_structured(
        profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA
    )

    assert response.data == _DECISION
    assert sleeps == [0.25]
    assert len(fake.invocations) == 2


def test_exhausted_budget_raises_agent_runtime_error() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    fake.enqueue_error(ModelTimeoutError("boom"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps, max_attempts=2))

    with pytest.raises(AgentRuntimeError) as excinfo:
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert excinfo.value.attempts == 2
    assert excinfo.value.last_invocation is not None
    assert sleeps == [0.25]


def test_sleep_is_not_called_after_the_final_attempt() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("boom"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps, max_attempts=1))

    with pytest.raises(AgentRuntimeError):
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert sleeps == []


def test_non_retryable_error_fails_fast_without_retry() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelRequestError("bad request"))
    sleeps: list[float] = []
    runtime = AgentRuntime(fake, _policy(sleeps))

    with pytest.raises(AgentRuntimeMisconfiguredError) as excinfo:
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    assert excinfo.value.attempts == 1
    assert excinfo.value.last_invocation is not None
    assert len(fake.invocations) == 1
    assert sleeps == []


class _RecordingGateway:
    """Records the exact request the runtime builds, then fails retryably."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self.schemas: list[Mapping[str, Any]] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        raise ModelTimeoutError("boom")

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self.requests.append(request)
        self.schemas.append(schema)
        raise ModelTimeoutError("boom")


def test_request_is_built_from_the_profile() -> None:
    gateway = _RecordingGateway()
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=1))

    with pytest.raises(AgentRuntimeError):
        runtime.decide_structured(profile=_PROFILE, system=_SYSTEM, user=_USER, schema=_SCHEMA)

    request = gateway.requests[0]
    assert request.model == "test-model"
    assert request.temperature == 0.1
    assert request.max_tokens == 64
    assert request.messages == (
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=_USER),
    )
    assert gateway.schemas[0] == _SCHEMA
```

(6 tests. `FakeModelGateway.enqueue_error` attaches an `LLMInvocation` to the raised error and records it, so `last_invocation` and `fake.invocations` assertions hold.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/agents/test_runtime.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai.agents.runtime'`

- [ ] **Step 3: Implement**

`src/ai/agents/runtime.py`:

```python
"""Synchronous decision runtime bridging the async model gateway."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.retry import RetryPolicy, is_retryable
from ai.models.errors import ModelError
from ai.models.gateway import ModelGateway
from ai.models.profiles import ModelProfile
from ai.models.types import LLMInvocation, Message, StructuredModelResponse


class AgentRuntime:
    """One bounded decision request per call; transport retries live here."""

    def __init__(self, gateway: ModelGateway, retry_policy: RetryPolicy | None = None) -> None:
        self._gateway = gateway
        self._retry_policy = retry_policy if retry_policy is not None else RetryPolicy()

    def decide_structured(
        self,
        *,
        profile: ModelProfile,
        system: str,
        user: str,
        schema: Mapping[str, Any],
    ) -> StructuredModelResponse:
        """Build one request from the profile and run it under the retry budget."""
        request = profile.to_request(
            [
                Message(role="system", content=system),
                Message(role="user", content=user),
            ]
        )
        last_error: ModelError | None = None
        last_invocation: LLMInvocation | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                return asyncio.run(self._gateway.generate_structured(request, schema))
            except ModelError as error:
                last_error = error
                last_invocation = error.invocation
                if not is_retryable(error):
                    raise AgentRuntimeMisconfiguredError(
                        f"non-retryable model failure after {attempt} attempt(s): {error}",
                        attempts=attempt,
                        last_invocation=error.invocation,
                    ) from error
                if attempt < self._retry_policy.max_attempts:
                    self._retry_policy.sleep(self._retry_policy.backoff_seconds)
        raise AgentRuntimeError(
            f"model decision failed after {self._retry_policy.max_attempts} attempt(s): {last_error}",
            attempts=self._retry_policy.max_attempts,
            last_invocation=last_invocation,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/agents/test_runtime.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **240** offline tests pass (baseline 221 + 13 from Task 1 + 6 here); the live smoke test passes/skips per `OPENROUTER_API_KEY`.

- [ ] **Step 6: Commit**

```bash
git add src/ai/agents/runtime.py tests/ai/agents/test_runtime.py
git commit -m "feat(ai): add synchronous AgentRuntime decision loop over the model gateway

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Agent profiles — `application/agents/profiles.py` + `config/agents.toml`

**Files:**
- Create: `src/application/agents/__init__.py` (docstring: `"""Game-aware character agents on top of the ai.agents runtime."""`)
- Create: `src/application/agents/profiles.py`
- Create: `config/agents.toml`
- Test: `tests/application/agents/test_profiles.py`

**Interfaces:**
- Consumes: `domain.character.character.CharacterClass` (StrEnum: `fighter`, `rogue`, `wizard`, `cleric`; `CharacterClass(value)` raises `ValueError` for unknown values).
- Produces: `AgentProfile(name, character_name, character_class, persona, objective, model_profile)` (frozen dataclass, all `str`); `AgentProfileCatalog(max_action_retries: int, agents: Mapping[str, AgentProfile])` with `get(name) -> AgentProfile` raising `AgentProfileNotFoundError`; `load_agent_profiles(path: str | Path) -> AgentProfileCatalog`; `AgentProfileError(ValueError)`; `AgentProfileNotFoundError(KeyError)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/agents/test_profiles.py`:

```python
"""Agent profile catalog loading tests."""

from pathlib import Path

import pytest

from application.agents.profiles import (
    AgentProfileCatalog,
    AgentProfileError,
    AgentProfileNotFoundError,
    load_agent_profiles,
)

_SHIPPED = Path(__file__).resolve().parents[3] / "config" / "agents.toml"

_VALID = """\
[agent]
max_action_retries = 2

[agents.brix]
character_name = "Brix"
character_class = "fighter"
persona = "A cautious sellsword."
objective = "Engage the nearest threat."
model_profile = "player"
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agents.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_shipped_config() -> None:
    catalog = load_agent_profiles(_SHIPPED)
    assert catalog.max_action_retries == 2
    brix = catalog.get("brix")
    assert brix.character_name == "Brix"
    assert brix.character_class == "fighter"
    assert brix.model_profile == "player"


def test_defaults_when_agent_table_missing(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "rogue"\n'
        'persona = "p"\nobjective = "o"\nmodel_profile = "player"\n',
    )
    catalog = load_agent_profiles(path)
    assert catalog.max_action_retries == 2


def test_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "fighter"\n'
        'persona = "p"\nmodel_profile = "player"\n',
    )
    with pytest.raises(AgentProfileError, match="missing fields"):
        load_agent_profiles(path)


def test_unknown_character_class_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "bard"\n'
        'persona = "p"\nobjective = "o"\nmodel_profile = "player"\n',
    )
    with pytest.raises(AgentProfileError, match="character_class"):
        load_agent_profiles(path)


def test_non_string_field_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[agents.brix]\ncharacter_name = "B"\ncharacter_class = "fighter"\n'
        'persona = "p"\nobjective = "o"\nmodel_profile = 3\n',
    )
    with pytest.raises(AgentProfileError, match="model_profile"):
        load_agent_profiles(path)


def test_empty_agents_table_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "[agent]\nmax_action_retries = 1\n")
    with pytest.raises(AgentProfileError, match="at least one agent"):
        load_agent_profiles(path)


def test_negative_retries_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID.replace("max_action_retries = 2", "max_action_retries = -1"))
    with pytest.raises(AgentProfileError, match="max_action_retries"):
        load_agent_profiles(path)


def test_unknown_agent_name_raises_not_found() -> None:
    catalog = AgentProfileCatalog(max_action_retries=2, agents={})
    with pytest.raises(AgentProfileNotFoundError):
        catalog.get("nobody")
```

(8 tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_profiles.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.agents'`

- [ ] **Step 3: Implement**

`src/application/agents/__init__.py`:

```python
"""Game-aware character agents on top of the ai.agents runtime."""
```

`src/application/agents/profiles.py`:

```python
"""Agent profile configuration (mirrors ai.models.profiles' load-and-validate pattern)."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.character.character import CharacterClass


class AgentProfileError(ValueError):
    """Raised when config/agents.toml has a structurally invalid shape."""


class AgentProfileNotFoundError(KeyError):
    """Raised when an unknown agent profile name is requested."""


@dataclass(frozen=True)
class AgentProfile:
    name: str
    character_name: str
    character_class: str
    persona: str
    objective: str
    model_profile: str


@dataclass(frozen=True)
class AgentProfileCatalog:
    max_action_retries: int
    agents: Mapping[str, AgentProfile]

    def get(self, name: str) -> AgentProfile:
        try:
            return self.agents[name]
        except KeyError:
            raise AgentProfileNotFoundError(f"unknown agent profile: {name}") from None


def load_agent_profiles(path: str | Path) -> AgentProfileCatalog:
    """Load [agent] and [agents.*] tables; structure validation only."""
    with Path(path).open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)

    agent_table = data.get("agent", {})
    if not isinstance(agent_table, dict):
        raise AgentProfileError("[agent] must be a table")

    retries = agent_table.get("max_action_retries", 2)
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise AgentProfileError("[agent] max_action_retries must be an int >= 0")

    agents_table = data.get("agents", {})
    if not isinstance(agents_table, dict) or not agents_table:
        raise AgentProfileError("[agents] must define at least one agent")

    agents: dict[str, AgentProfile] = {}
    for name, entry in agents_table.items():
        if not isinstance(entry, dict):
            raise AgentProfileError(f"[agents.{name}] must be a table")
        required = {"character_name", "character_class", "persona", "objective", "model_profile"}
        missing = required - set(entry)
        if missing:
            raise AgentProfileError(f"[agents.{name}] missing fields: {sorted(missing)}")
        try:
            CharacterClass(entry["character_class"])
        except ValueError:
            valid = ", ".join(cls.value for cls in CharacterClass)
            raise AgentProfileError(
                f"[agents.{name}] character_class '{entry['character_class']}' "
                f"is not one of: {valid}"
            ) from None
        for field_name in ("character_name", "persona", "objective", "model_profile"):
            value = entry[field_name]
            if not isinstance(value, str) or not value:
                raise AgentProfileError(f"[agents.{name}] {field_name} must be a non-empty string")
        agents[name] = AgentProfile(
            name=name,
            character_name=entry["character_name"],
            character_class=entry["character_class"],
            persona=entry["persona"],
            objective=entry["objective"],
            model_profile=entry["model_profile"],
        )

    return AgentProfileCatalog(max_action_retries=retries, agents=agents)
```

`config/agents.toml`:

```toml
[agent]
max_action_retries = 2

[agents.brix]
character_name = "Brix"
character_class = "fighter"
persona = "A cautious sellsword who prefers finishing fights quickly and safely."
objective = "Survive the skirmish and protect Arin; engage the nearest threat."
model_profile = "player"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_profiles.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **248** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents config/agents.toml tests/application/agents
git commit -m "feat(application): add agent profile catalog and shipped config/agents.toml

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Perception — the information-asymmetry boundary (CLAUDE.md §20)

**Files:**
- Create: `src/application/agents/perception.py`
- Test: `tests/application/agents/test_perception.py`

**Interfaces:**
- Consumes: `application.views.{GameView, CharacterView, CombatView, InitiativeEntryView}` — `CharacterView(id, name, character_class: str | None, level, hp_current, hp_max, armor_class, conditions: list[str], is_defeated)`; `CombatView(round_number, status, active_actor_id: str | None, initiative_order: list[InitiativeEntryView])`; `InitiativeEntryView(character_id, name, total)`.
- Produces: `OpponentBrief(id: str, name: str, is_defeated: bool)`; `AgentPerception(round_number: int, active_actor_id: str, self_view: CharacterView, opponents: tuple[OpponentBrief, ...], initiative_order: tuple[str, ...])`; `build_perception(view: GameView, actor_id: str) -> AgentPerception`; `first_living_opponent(view: GameView, actor_id: str) -> str | None`; `AgentNotInCombatError(RuntimeError)`. Opponents carry name + defeated status ONLY — no HP/AC anywhere on `OpponentBrief`.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/agents/test_perception.py`:

```python
"""Perception projection tests — the §20 information-asymmetry boundary."""

from dataclasses import fields, replace

import pytest

from application.agents.perception import (
    AgentNotInCombatError,
    OpponentBrief,
    build_perception,
    first_living_opponent,
)
from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
)


def _character(character_id: str, name: str, *, defeated: bool = False) -> CharacterView:
    return CharacterView(
        id=character_id,
        name=name,
        character_class=None if name == "Goblin" else "fighter",
        level=1,
        hp_current=0 if defeated else 5,
        hp_max=12,
        armor_class=16,
        conditions=[],
        is_defeated=defeated,
    )


def _view(*, active: str = "brix", goblin_defeated: bool = False) -> GameView:
    combat = CombatView(
        round_number=2,
        status="active",
        active_actor_id=active,
        initiative_order=[
            InitiativeEntryView(character_id="brix", name="Brix", total=18),
            InitiativeEntryView(character_id="gob", name="Goblin", total=9),
        ],
    )
    return GameView(
        game_id="g1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[_character("arin", "Arin"), _character("brix", "Brix")],
        enemies=[_character("gob", "Goblin", defeated=goblin_defeated)],
        combat=combat,
    )


def test_perception_projects_self_and_opponent_briefs() -> None:
    perception = build_perception(_view(), "brix")
    assert perception.round_number == 2
    assert perception.active_actor_id == "brix"
    assert perception.self_view.id == "brix"
    assert perception.self_view.hp_current == 5
    assert perception.opponents == (
        OpponentBrief(id="gob", name="Goblin", is_defeated=False),
    )
    assert perception.initiative_order == ("Brix", "Goblin")


def test_opponent_briefs_carry_no_hp_or_ac() -> None:
    perception = build_perception(_view(), "brix")
    brief_fields = {field.name for field in fields(OpponentBrief)}
    assert brief_fields == {"id", "name", "is_defeated"}
    brief = perception.opponents[0]
    assert not hasattr(brief, "hp_current")
    assert not hasattr(brief, "armor_class")


def test_not_your_turn_raises() -> None:
    with pytest.raises(AgentNotInCombatError):
        build_perception(_view(active="arin"), "brix")


def test_no_active_combat_raises() -> None:
    view = _view(active="brix")
    with pytest.raises(AgentNotInCombatError):
        build_perception(replace(view, combat=None), "brix")


def test_enemy_side_actor_is_supported() -> None:
    perception = build_perception(_view(active="gob"), "gob")
    assert perception.self_view.id == "gob"
    assert {opponent.id for opponent in perception.opponents} == {"arin", "brix"}


def test_first_living_opponent_from_party_side() -> None:
    assert first_living_opponent(_view(), "brix") == "gob"


def test_first_living_opponent_returns_none_when_all_defeated() -> None:
    assert first_living_opponent(_view(goblin_defeated=True), "brix") is None


def test_first_living_opponent_from_enemy_side() -> None:
    assert first_living_opponent(_view(active="gob"), "gob") == "arin"
```

(8 tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_perception.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.agents.perception'`

- [ ] **Step 3: Implement**

`src/application/agents/perception.py`:

```python
"""The information-asymmetry boundary (CLAUDE.md §20): perception by field selection."""

from __future__ import annotations

from dataclasses import dataclass

from application.views import CharacterView, GameView


class AgentNotInCombatError(RuntimeError):
    """Raised when the actor is not the active combatant in a running combat."""


@dataclass(frozen=True)
class OpponentBrief:
    """What an agent may know about an opponent: identity and standing, never HP/AC."""

    id: str
    name: str
    is_defeated: bool


@dataclass(frozen=True)
class AgentPerception:
    round_number: int
    active_actor_id: str
    self_view: CharacterView
    opponents: tuple[OpponentBrief, ...]
    initiative_order: tuple[str, ...]


def _find(characters: list[CharacterView], actor_id: str) -> CharacterView | None:
    for character in characters:
        if character.id == actor_id:
            return character
    return None


def _opponents_of(view: GameView, self_view: CharacterView) -> list[CharacterView]:
    is_party = any(character.id == self_view.id for character in view.party)
    return view.enemies if is_party else view.party


def build_perception(view: GameView, actor_id: str) -> AgentPerception:
    """Project the actor's slice of the GameView; opponents are name + defeated status only."""
    if view.combat is None or view.combat.active_actor_id is None:
        raise AgentNotInCombatError(f"character {actor_id} has no active combat turn")
    if view.combat.active_actor_id != actor_id:
        raise AgentNotInCombatError(
            f"character {actor_id} is not the active combatant "
            f"(active: {view.combat.active_actor_id})"
        )
    self_view = _find(view.party, actor_id) or _find(view.enemies, actor_id)
    if self_view is None:
        raise AgentNotInCombatError(f"character {actor_id} is not part of this game")

    opponents = tuple(
        OpponentBrief(id=character.id, name=character.name, is_defeated=character.is_defeated)
        for character in _opponents_of(view, self_view)
    )
    initiative_order = tuple(entry.name for entry in view.combat.initiative_order)
    return AgentPerception(
        round_number=view.combat.round_number,
        active_actor_id=view.combat.active_actor_id,
        self_view=self_view,
        opponents=opponents,
        initiative_order=initiative_order,
    )


def first_living_opponent(view: GameView, actor_id: str) -> str | None:
    """The deterministic fallback target: the first living opponent of the actor's side."""
    self_view = _find(view.party, actor_id) or _find(view.enemies, actor_id)
    if self_view is None:
        raise AgentNotInCombatError(f"character {actor_id} is not part of this game")
    for character in _opponents_of(view, self_view):
        if not character.is_defeated:
            return character.id
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_perception.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **256** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/perception.py tests/application/agents/test_perception.py
git commit -m "feat(application): add game-view perception with information asymmetry

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: `CharacterAgent` — prompts + structured-decision mapping

**Files:**
- Create: `src/application/agents/character_agent.py`
- Test: `tests/application/agents/test_character_agent.py`

**Interfaces:**
- Consumes: Task 3's `AgentProfile`; Task 4's `AgentPerception`, `OpponentBrief`; `domain.rules.actions.AttackProposal(actor_id: CharacterId, target_id: CharacterId, weapon_id: str | None = None)`; `domain.common.ids.CharacterId`; `ai.models.schema.validate_against_schema(data, schema)` (raises `ModelInvalidResponseError`).
- Produces: `ATTACK_DECISION_SCHEMA: Mapping[str, Any]` (action_type enum ["attack"], target_id, public_message; all required; `additionalProperties: False`); `AgentDecision(proposal: AttackProposal, public_message: str)` (frozen; no invocation field — the service accumulates invocations); `CharacterAgent(profile)` with `build_system_prompt() -> str`, `build_user_prompt(perception, *, rejection: str | None = None) -> str`, `map_decision(data: Mapping[str, Any], perception: AgentPerception) -> AgentDecision`; `InvalidAgentDecisionError(ValueError)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/agents/test_character_agent.py`:

```python
"""CharacterAgent prompt and decision-mapping tests."""

from typing import Any

import pytest

from ai.models.errors import ModelInvalidResponseError
from ai.models.schema import validate_against_schema
from application.agents.character_agent import (
    ATTACK_DECISION_SCHEMA,
    CharacterAgent,
    InvalidAgentDecisionError,
)
from application.agents.perception import AgentPerception, OpponentBrief
from application.agents.profiles import AgentProfile
from application.views import CharacterView
from domain.common.ids import CharacterId

_PROFILE = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword who prefers finishing fights quickly and safely.",
    objective="Survive the skirmish and protect Arin; engage the nearest threat.",
    model_profile="player",
)


def _perception(**overrides: Any) -> AgentPerception:
    me = CharacterView(
        id="brix",
        name="Brix",
        character_class="fighter",
        level=1,
        hp_current=10,
        hp_max=12,
        armor_class=16,
        conditions=[],
        is_defeated=False,
    )
    values: dict[str, Any] = {
        "round_number": 2,
        "active_actor_id": "brix",
        "self_view": me,
        "opponents": (
            OpponentBrief(id="gob", name="Goblin", is_defeated=False),
            OpponentBrief(id="orc", name="Orc", is_defeated=True),
        ),
        "initiative_order": ("Brix", "Goblin", "Arin"),
    }
    values.update(overrides)
    return AgentPerception(**values)


def test_system_prompt_carries_persona_objective_and_rules() -> None:
    prompt = CharacterAgent(_PROFILE).build_system_prompt()
    assert "Brix" in prompt
    assert "cautious sellsword" in prompt
    assert "protect Arin" in prompt
    assert "attack" in prompt
    assert "target_id" in prompt


def test_user_prompt_lists_opponents_but_never_enemy_hp() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception())
    assert "- gob: Goblin (standing)" in prompt
    assert "- orc: Orc (defeated)" in prompt
    assert "HP 10/12" in prompt
    assert prompt.count("HP") == 1  # own HP line only — no enemy HP anywhere
    assert prompt.count("AC") == 1  # own AC line only — no enemy AC anywhere
    assert "Turn order: Brix, Goblin, Arin" in prompt


def test_rejection_feedback_is_appended() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(
        _perception(), rejection="target 'orc' is not a living opponent"
    )
    assert "rejected: target 'orc' is not a living opponent" in prompt


def test_map_decision_builds_attack_proposal() -> None:
    decision = CharacterAgent(_PROFILE).map_decision(
        {"action_type": "attack", "target_id": "gob", "public_message": " I strike! "},
        _perception(),
    )
    assert decision.proposal.actor_id == CharacterId("brix")
    assert decision.proposal.target_id == CharacterId("gob")
    assert decision.proposal.weapon_id is None
    assert decision.public_message == "I strike!"


def test_map_decision_rejects_dead_target() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="not a living opponent"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "attack", "target_id": "orc", "public_message": "hi"},
            _perception(),
        )


def test_map_decision_rejects_unknown_target() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="not a living opponent"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "attack", "target_id": "nobody", "public_message": "hi"},
            _perception(),
        )


def test_map_decision_rejects_unsupported_action_type() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="action_type"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "dodge", "target_id": "gob", "public_message": "hi"},
            _perception(),
        )


def test_map_decision_rejects_empty_public_message() -> None:
    with pytest.raises(InvalidAgentDecisionError, match="public_message"):
        CharacterAgent(_PROFILE).map_decision(
            {"action_type": "attack", "target_id": "gob", "public_message": "   "},
            _perception(),
        )


def test_schema_accepts_a_valid_decision() -> None:
    validate_against_schema(
        {"action_type": "attack", "target_id": "gob", "public_message": "I attack."},
        ATTACK_DECISION_SCHEMA,
    )  # does not raise


def test_schema_rejects_extra_keys_and_other_actions() -> None:
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {"action_type": "attack", "target_id": "gob", "public_message": "x", "extra": 1},
            ATTACK_DECISION_SCHEMA,
        )
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {"action_type": "cast_spell", "target_id": "gob", "public_message": "x"},
            ATTACK_DECISION_SCHEMA,
        )
```

(10 tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_character_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.agents.character_agent'`

- [ ] **Step 3: Implement**

`src/application/agents/character_agent.py`:

```python
"""One character agent: identity, prompts, and structured-decision mapping."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from application.agents.perception import AgentPerception
from application.agents.profiles import AgentProfile
from domain.common.ids import CharacterId
from domain.rules.actions import AttackProposal

ATTACK_DECISION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["attack"]},
        "target_id": {"type": "string"},
        "public_message": {"type": "string"},
    },
    "required": ["action_type", "target_id", "public_message"],
    "additionalProperties": False,
}


class InvalidAgentDecisionError(ValueError):
    """The model's decision failed agent-level mapping (unknown/dead target, bad fields)."""


@dataclass(frozen=True)
class AgentDecision:
    proposal: AttackProposal
    public_message: str


class CharacterAgent:
    """Prompt construction and decision mapping for one agent-controlled character."""

    def __init__(self, profile: AgentProfile) -> None:
        self._profile = profile

    def build_system_prompt(self) -> str:
        return (
            f"You are {self._profile.character_name}, a {self._profile.character_class} "
            "in a tabletop role-playing combat.\n"
            f"Personality: {self._profile.persona}\n"
            f"Objective: {self._profile.objective}\n"
            "\n"
            "Rules:\n"
            "- You may only take the attack action.\n"
            "- Choose exactly one target_id from the opponents listed in the user message.\n"
            '- Reply ONLY with a JSON object: action_type ("attack"), target_id (string), '
            "public_message (a short first-person battle cry or rationale; never hidden "
            "reasoning).\n"
            "- No other keys, no prose outside the JSON."
        )

    def build_user_prompt(
        self, perception: AgentPerception, *, rejection: str | None = None
    ) -> str:
        me = perception.self_view
        conditions = ", ".join(me.conditions) if me.conditions else "none"
        lines = [
            f"Round {perception.round_number}. It is your turn.",
            f"You: {me.name} (level {me.level}, {me.character_class}), "
            f"HP {me.hp_current}/{me.hp_max}, AC {me.armor_class}, "
            f"conditions: {conditions}.",
            "Opponents:",
        ]
        lines.extend(
            f"- {opponent.id}: {opponent.name} "
            f"({'defeated' if opponent.is_defeated else 'standing'})"
            for opponent in perception.opponents
        )
        lines.append(f"Turn order: {', '.join(perception.initiative_order)}")
        if rejection is not None:
            lines.append(f"Your previous action was rejected: {rejection}. Choose again.")
        return "\n".join(lines)

    def map_decision(
        self, data: Mapping[str, Any], perception: AgentPerception
    ) -> AgentDecision:
        if data.get("action_type") != "attack":
            raise InvalidAgentDecisionError(f"unsupported action_type: {data.get('action_type')!r}")

        target_id = data.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            raise InvalidAgentDecisionError("target_id must be a non-empty string")

        living = {
            opponent.id: opponent
            for opponent in perception.opponents
            if not opponent.is_defeated
        }
        if target_id not in living:
            raise InvalidAgentDecisionError(
                f"target '{target_id}' is not a living opponent (living: {sorted(living)})"
            )

        public_message = data.get("public_message")
        if not isinstance(public_message, str) or not public_message.strip():
            raise InvalidAgentDecisionError("public_message must be a non-empty string")

        return AgentDecision(
            proposal=AttackProposal(
                actor_id=CharacterId(perception.active_actor_id),
                target_id=CharacterId(target_id),
            ),
            public_message=public_message.strip(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_character_agent.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **266** offline tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/character_agent.py tests/application/agents/test_character_agent.py
git commit -m "feat(application): add character agent prompts and decision mapping

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: `ScriptedAgentGateway` + `AgentTurnService` — the decision-attempt loop

**Files:**
- Create: `src/application/agents/fake_script.py`
- Create: `src/application/agents/agent_turn_service.py`
- Test: `tests/application/agents/test_fake_script.py`
- Test: `tests/application/agents/test_agent_turn_service.py`

**Interfaces:**
- Consumes: Tasks 1–5 (`AgentRuntime`, `RetryPolicy`, `AgentRuntimeError`, **`AgentRuntimeMisconfiguredError` — re-raise it before catching `AgentRuntimeError`, since it subclasses the latter**); `AgentProfile`/`AgentProfileCatalog`; `build_perception`/`first_living_opponent`/`AgentNotInCombatError`; `CharacterAgent`/`ATTACK_DECISION_SCHEMA`/`AgentDecision`/`InvalidAgentDecisionError`; `GameService` (`get_view`, `submit_action`); `SubmitActionCommand(game_id, actor_id, action_type, target_id)`; `ai.models.profiles.{ModelProfileCatalog, ModelProfile}`; `ai.models.fake.FakeModelGateway` (`.enqueue_structured(dict)` — schema-validated at call time); `application.views.TurnReport(game_id: str, accepted: bool, error_code: str, reason: str, events, view, game_over)`; `ai.models.types.LLMInvocation`.
- Produces: `ScriptedAgentGateway(inner: FakeModelGateway, decision: Callable[[], Mapping[str, Any]])` satisfying `ModelGateway`; `AgentTurnReport(actor_id: str, accepted: bool, proposal_source: str, action_attempts: int, rejection_reasons: tuple[str, ...], fallback_reason: str | None, public_message: str | None, invocations: tuple[LLMInvocation, ...], turn_report: TurnReport)`; `AgentTurnService(game_service, runtime, catalog: ModelProfileCatalog, agent_profiles: AgentProfileCatalog, *, max_action_retries: int | None = None)` with `register(actor_id: CharacterId, profile: AgentProfile) -> None`, `is_agent_controlled(actor_id: CharacterId) -> bool`, `take_turn(game_id: GameId, actor_id: CharacterId) -> AgentTurnReport`; `AgentNotRegisteredError(KeyError)`.

- [ ] **Step 1: Write the failing tests (scripted gateway)**

Create `tests/application/agents/test_fake_script.py`:

```python
"""ScriptedAgentGateway tests — the offline decision source."""

import asyncio

import pytest

from ai.models.errors import ModelInvalidResponseError
from ai.models.fake import FakeModelGateway
from ai.models.types import Message, ModelRequest
from application.agents.fake_script import ScriptedAgentGateway

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def _request() -> ModelRequest:
    return ModelRequest(messages=(Message(role="user", content="decide"),), model="test-model")


def test_reenqueue_the_decision_before_every_structured_call() -> None:
    inner = FakeModelGateway()
    calls: list[int] = []

    def _decision() -> dict[str, str]:
        calls.append(len(calls))
        return {"answer": f"ok-{len(calls)}"}

    gateway = ScriptedAgentGateway(inner, _decision)

    first = asyncio.run(gateway.generate_structured(_request(), _SCHEMA))
    second = asyncio.run(gateway.generate_structured(_request(), _SCHEMA))

    assert first.data == {"answer": "ok-1"}
    assert second.data == {"answer": "ok-2"}
    assert len(calls) == 2


def test_scripted_decisions_pass_real_schema_validation() -> None:
    gateway = ScriptedAgentGateway(FakeModelGateway(), lambda: {"answer": 3})

    with pytest.raises(ModelInvalidResponseError):
        asyncio.run(gateway.generate_structured(_request(), _SCHEMA))


def test_text_calls_pass_through_to_the_inner_gateway() -> None:
    inner = FakeModelGateway()
    inner.enqueue_text("hello")
    gateway = ScriptedAgentGateway(inner, lambda: {"answer": "unused"})

    response = asyncio.run(gateway.generate(_request()))

    assert response.text == "hello"
```

(3 tests.)

- [ ] **Step 2: Write the failing tests (turn service)**

Create `tests/application/agents/test_agent_turn_service.py`:

```python
"""AgentTurnService decision-loop tests (scripted fake gateway, no real LLM)."""

import pytest

from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelTimeoutError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import ModelProfile, ModelProfileCatalog
from application.agents.agent_turn_service import AgentNotRegisteredError, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway
from application.agents.profiles import AgentProfile, AgentProfileCatalog
from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from domain.common.ids import CharacterId, GameId
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository

_MODEL_CATALOG = ModelProfileCatalog(
    default_provider="fake",
    profiles={
        "player": ModelProfile(
            name="player",
            provider="fake",
            model="test-model",
            temperature=0.1,
            max_tokens=64,
        )
    },
    pricing={},
)
_BRIX = AgentProfile(
    name="brix",
    character_name="Brix",
    character_class="fighter",
    persona="A cautious sellsword.",
    objective="Engage the nearest threat.",
    model_profile="player",
)


def _game_service() -> GameService:
    event_store = InMemoryEventRepository()
    return GameService(InMemoryGameRepository(event_store), event_store)


def _fighter(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword",
            name="Longsword",
            damage_die_count=1,
            damage_die_size=8,
        ),
    )


def _goblin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Goblin",
        character_type="enemy",
        level=1,
        strength=8,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=8,
        charisma=8,
        armor_class=13,
        speed_ft=30,
        max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar",
            name="Scimitar",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _party_with_brix_first(
    game_service: GameService,
) -> tuple[GameId, CharacterId, CharacterId]:
    """Create Arin + Brix + Goblin and start combat; find a seed where Brix acts first."""
    for seed in range(1, 500):
        game_id = game_service.create_game(CreateGameCommand(seed=seed))
        game_service.add_character(game_id, _fighter("Arin"))
        brix_id = game_service.add_character(game_id, _fighter("Brix"))
        goblin_id = game_service.add_character(game_id, _goblin())
        game_service.start_combat(game_id)
        view = game_service.get_view(game_id)
        if view.combat is not None and view.combat.active_actor_id == brix_id.value:
            return game_id, brix_id, goblin_id
    raise AssertionError("no seed in 1..499 lets Brix act first")


def _agent_service(
    game_service: GameService,
    gateway: FakeModelGateway,
    *,
    max_action_retries: int = 2,
) -> AgentTurnService:
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=3))
    agent_profiles = AgentProfileCatalog(
        max_action_retries=max_action_retries,
        agents={"brix": _BRIX},
    )
    return AgentTurnService(game_service, runtime, _MODEL_CATALOG, agent_profiles)


def test_model_decision_is_accepted_on_the_first_attempt() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    service = _agent_service(game_service, fake)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    assert report.proposal_source == "model"
    assert report.action_attempts == 1
    assert report.public_message == "I strike."
    assert report.fallback_reason is None
    assert len(report.invocations) == 1
    assert report.turn_report.accepted is True
    assert any(event.event_type == "attack_resolved" for event in report.turn_report.events)


def test_invalid_target_is_fed_back_and_retried() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": "nobody", "public_message": "Who?"}
    )
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "There!"}
    )
    service = _agent_service(game_service, fake)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    assert report.proposal_source == "model"
    assert report.action_attempts == 2
    assert len(report.rejection_reasons) == 1
    assert "not a living opponent" in report.rejection_reasons[0]
    assert len(report.invocations) == 2


def test_transport_exhaustion_falls_back_deterministically() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(6):  # 2 decision attempts x 3 transport attempts
        fake.enqueue_error(ModelTimeoutError("boom"))
    service = _agent_service(game_service, fake, max_action_retries=1)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert report.accepted is True
    assert report.action_attempts == 2
    assert report.fallback_reason is not None
    assert len(report.invocations) == 2  # last invocation of each exhausted runtime call


def test_decision_exhaustion_falls_back_deterministically() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(2):  # max_action_retries=1 -> 2 decision attempts, both invalid
        fake.enqueue_structured(
            {"action_type": "attack", "target_id": "nobody", "public_message": "Who?"}
        )
    service = _agent_service(game_service, fake, max_action_retries=1)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert report.accepted is True
    assert report.turn_report.accepted is True


def test_take_turn_for_unregistered_actor_raises() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    service = _agent_service(game_service, FakeModelGateway())

    with pytest.raises(AgentNotRegisteredError):
        service.take_turn(game_id, brix_id)


def test_full_fight_completes_with_the_agent_in_the_party() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)

    def _decision() -> dict[str, str]:
        view = game_service.get_view(game_id)
        target = next(enemy for enemy in view.enemies if not enemy.is_defeated)
        return {"action_type": "attack", "target_id": target.id, "public_message": "I attack."}

    gateway = ScriptedAgentGateway(FakeModelGateway(), _decision)
    service = _agent_service(game_service, gateway)
    service.register(brix_id, _BRIX)

    for _ in range(200):
        view = game_service.get_view(game_id)
        if view.status == "ended":
            break
        active = view.combat.active_actor_id if view.combat else None
        if active is None:
            break
        if active == brix_id.value:
            service.take_turn(game_id, brix_id)
        elif active == goblin_id.value:
            game_service.run_active_enemy_turns(game_id)
        else:
            game_service.submit_action(
                SubmitActionCommand(
                    game_id=game_id,
                    actor_id=CharacterId(active),
                    action_type="attack",
                    target_id=goblin_id,
                )
            )

    assert game_service.get_view(game_id).status == "ended"
```

(6 tests. Character ids are generated uuids, so the goblin's id is captured at runtime — never hardcoded. Event envelopes expose `.event_type` as the snake_case class name, so `AttackResolved` → `"attack_resolved"`.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_fake_script.py tests/application/agents/test_agent_turn_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.agents.fake_script'`

- [ ] **Step 4: Implement**

`src/application/agents/fake_script.py`:

```python
"""Scripted decisions for --agent fake and offline tests: the queue never exhausts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ai.models.fake import FakeModelGateway
from ai.models.types import ModelRequest, ModelResponse, StructuredModelResponse


class ScriptedAgentGateway:
    """Wraps a FakeModelGateway and re-enqueues a canned decision before every call."""

    def __init__(
        self,
        inner: FakeModelGateway,
        decision: Callable[[], Mapping[str, Any]],
    ) -> None:
        self._inner = inner
        self._decision = decision

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self._inner.generate(request)

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        self._inner.enqueue_structured(dict(self._decision()))
        return await self._inner.generate_structured(request, schema)
```

`src/application/agents/agent_turn_service.py`:

```python
"""The agent turn use case: decision-attempt loop over the model, fallback, reporting."""

from __future__ import annotations

from dataclasses import dataclass

from ai.agents.errors import AgentRuntimeError, AgentRuntimeMisconfiguredError
from ai.agents.runtime import AgentRuntime
from ai.models.profiles import ModelProfileCatalog
from ai.models.types import LLMInvocation
from application.agents.character_agent import (
    ATTACK_DECISION_SCHEMA,
    AgentDecision,
    CharacterAgent,
    InvalidAgentDecisionError,
)
from application.agents.perception import (
    AgentNotInCombatError,
    build_perception,
    first_living_opponent,
)
from application.agents.profiles import AgentProfile, AgentProfileCatalog
from application.commands import SubmitActionCommand
from application.game_service import GameService
from application.views import TurnReport
from domain.common.ids import CharacterId, GameId


@dataclass(frozen=True)
class AgentTurnReport:
    actor_id: str
    accepted: bool
    proposal_source: str  # "model" | "fallback"
    action_attempts: int
    rejection_reasons: tuple[str, ...]
    fallback_reason: str | None
    public_message: str | None
    invocations: tuple[LLMInvocation, ...]
    turn_report: TurnReport


class AgentNotRegisteredError(KeyError):
    """Raised when take_turn is called for an actor with no registered agent profile."""


class AgentTurnService:
    """Runs one agent-controlled turn: bounded decisions, engine validation, fallback."""

    def __init__(
        self,
        game_service: GameService,
        runtime: AgentRuntime,
        catalog: ModelProfileCatalog,
        agent_profiles: AgentProfileCatalog,
        *,
        max_action_retries: int | None = None,
    ) -> None:
        self._game_service = game_service
        self._runtime = runtime
        self._catalog = catalog
        self._max_action_retries = (
            max_action_retries
            if max_action_retries is not None
            else agent_profiles.max_action_retries
        )
        self._agents: dict[str, AgentProfile] = {}

    def register(self, actor_id: CharacterId, profile: AgentProfile) -> None:
        self._agents[actor_id.value] = profile

    def is_agent_controlled(self, actor_id: CharacterId) -> bool:
        return actor_id.value in self._agents

    def take_turn(self, game_id: GameId, actor_id: CharacterId) -> AgentTurnReport:
        profile = self._agents.get(actor_id.value)
        if profile is None:
            raise AgentNotRegisteredError(actor_id.value)

        agent = CharacterAgent(profile)
        model_profile = self._catalog.get(profile.model_profile)
        invocations: list[LLMInvocation] = []
        rejection_reasons: list[str] = []
        rejection: str | None = None

        for attempt in range(1, self._max_action_retries + 2):
            view = self._game_service.get_view(game_id)
            perception = build_perception(view, actor_id.value)
            try:
                response = self._runtime.decide_structured(
                    profile=model_profile,
                    system=agent.build_system_prompt(),
                    user=agent.build_user_prompt(perception, rejection=rejection),
                    schema=ATTACK_DECISION_SCHEMA,
                )
                invocations.append(response.invocation)
                decision = agent.map_decision(response.data, perception)
            except AgentRuntimeMisconfiguredError:
                raise
            except AgentRuntimeError as error:
                if error.last_invocation is not None:
                    invocations.append(error.last_invocation)
                rejection = f"model failure: {error}"
                rejection_reasons.append(rejection)
                continue
            except InvalidAgentDecisionError as error:
                rejection = str(error)
                rejection_reasons.append(rejection)
                continue

            turn_report = self._submit(game_id, actor_id, decision)
            if turn_report.accepted:
                return AgentTurnReport(
                    actor_id=actor_id.value,
                    accepted=True,
                    proposal_source="model",
                    action_attempts=attempt,
                    rejection_reasons=tuple(rejection_reasons),
                    fallback_reason=None,
                    public_message=decision.public_message,
                    invocations=tuple(invocations),
                    turn_report=turn_report,
                )
            rejection = turn_report.reason or "action rejected by the rules engine"
            rejection_reasons.append(rejection)

        return self._fallback(game_id, actor_id, invocations, tuple(rejection_reasons))

    def _submit(
        self, game_id: GameId, actor_id: CharacterId, decision: AgentDecision
    ) -> TurnReport:
        return self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=decision.proposal.target_id,
            )
        )

    def _fallback(
        self,
        game_id: GameId,
        actor_id: CharacterId,
        invocations: list[LLMInvocation],
        rejection_reasons: tuple[str, ...],
    ) -> AgentTurnReport:
        view = self._game_service.get_view(game_id)
        target_id = first_living_opponent(view, actor_id.value)
        if target_id is None:
            raise AgentNotInCombatError(
                f"character {actor_id.value} has no living opponent to attack"
            )
        detail = "; ".join(rejection_reasons) if rejection_reasons else "no model decision"
        turn_report = self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=CharacterId(target_id),
            )
        )
        return AgentTurnReport(
            actor_id=actor_id.value,
            accepted=turn_report.accepted,
            proposal_source="fallback",
            action_attempts=self._max_action_retries + 1,
            rejection_reasons=rejection_reasons,
            fallback_reason=f"decision budget exhausted ({detail})",
            public_message=None,
            invocations=tuple(invocations),
            turn_report=turn_report,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents/test_fake_script.py tests/application/agents/test_agent_turn_service.py -q`
Expected: PASS (9 passed)

- [ ] **Step 6: Quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **275** offline tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/application/agents/fake_script.py src/application/agents/agent_turn_service.py tests/application/agents/test_fake_script.py tests/application/agents/test_agent_turn_service.py
git commit -m "feat(application): add agent turn service with bounded retries and fallback

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: CLI integration — `--agent off|llm|fake`

**Files:**
- Modify: `src/interfaces/cli/app.py`
- Test: `tests/interfaces/test_cli.py` (append 4 tests)

**Interfaces:**
- Consumes: everything from Tasks 1–6. `app.py` already imports `os`, `GameView`, `CharacterId`/`GameId`, `DomainError`; it needs `Path` and the new agent imports added.
- Produces: `--agent {off,llm,fake}` (default `off`); `_CONFIG_DIR` constant; `_fighter(name: str)` (replaces `_arin()`); `_wire_agent(service, game_id, mode, console) -> AgentTurnService`; `_render_agent_turn(console, report, view) -> None`. `off` keeps behavior byte-identical.

- [ ] **Step 1: Write the failing tests**

Append to `tests/interfaces/test_cli.py`:

```python
def test_main_agent_fake_plays_a_full_fight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(
        argv=["--agent", "fake"],
        console=console,
        input_fn=_scripted(*(["attack goblin"] * 60)),
    )
    assert code == 0
    output = buffer.getvalue()
    assert "AI-controlled" in output
    assert "wins the combat" in output


def test_main_agent_fake_agent_takes_a_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for seed in range(1, 60):
        console, buffer = _console()
        code = main(
            argv=["--agent", "fake", "--seed", str(seed)],
            console=console,
            input_fn=_scripted(*(["attack goblin"] * 60)),
        )
        assert code == 0
        output = buffer.getvalue()
        if "Agent:" in output:
            assert "wins the combat" in output
            assert "AI-controlled" in output
            return
    pytest.fail("no seed in 1..59 gave the agent a turn before the fight ended")


def test_main_agent_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=["--agent", "llm"], console=console, input_fn=_scripted())
    assert code == 2
    assert "OPENROUTER_API_KEY" in buffer.getvalue()


def test_main_agent_off_has_no_agent_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    console, buffer = _console()
    code = main(argv=[], console=console, input_fn=_scripted("/quit"))
    assert code == 0
    assert "AI-controlled" not in buffer.getvalue()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/interfaces/test_cli.py -q -k agent`
Expected: FAIL — `SystemExit: 2` from argparse (`--agent` is an unrecognized argument)

- [ ] **Step 3: Implement**

Edits to `src/interfaces/cli/app.py` (line numbers refer to the current 211-line file):

3a. Import block — add `from pathlib import Path` after `from collections.abc import Callable`, and add these first-party imports (ruff isort orders them; place per its output):

```python
from ai.agents.retry import RetryPolicy
from ai.agents.runtime import AgentRuntime
from ai.models.errors import ModelError
from ai.models.fake import FakeModelGateway
from ai.models.profiles import load_model_profiles
from application.agents.agent_turn_service import AgentTurnReport, AgentTurnService
from application.agents.fake_script import ScriptedAgentGateway
from application.agents.profiles import load_agent_profiles
from infrastructure.llm import create_gateway
```

3b. After the import block, add:

```python
_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
```

3c. Replace `_arin()` (lines 77–98) with a parameterized builder:

```python
def _fighter(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword",
            name="Longsword",
            damage_die_count=1,
            damage_die_size=8,
        ),
    )
```

3d. Below `_goblin()`, add:

```python
def _wire_agent(
    service: GameService,
    game_id: GameId,
    mode: str,
    console: Console,
) -> AgentTurnService:
    """Wire the agent stack and add Brix to the party before combat starts."""
    agent_profiles = load_agent_profiles(_CONFIG_DIR / "agents.toml")
    model_catalog = load_model_profiles(_CONFIG_DIR / "llm.toml")
    if mode == "llm":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set; export it to run with --agent llm")
        gateway = create_gateway(model_catalog.default_provider, api_key=api_key)
    else:
        fake = FakeModelGateway()

        def _decision() -> dict[str, str]:
            view = service.get_view(game_id)
            living = [enemy for enemy in view.enemies if not enemy.is_defeated]
            target = living[0] if living else view.enemies[0]
            return {
                "action_type": "attack",
                "target_id": target.id,
                "public_message": "I attack the nearest standing foe.",
            }

        gateway = ScriptedAgentGateway(fake, _decision)
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(service, runtime, model_catalog, agent_profiles)
    brix = agent_profiles.get("brix")
    brix_id = service.add_character(game_id, _fighter(brix.character_name))
    agent_service.register(brix_id, brix)
    console.print(
        f"[cyan]{brix.character_name} joins the party (AI-controlled, mode: {mode})[/cyan]"
    )
    return agent_service


def _render_agent_turn(console: Console, report: AgentTurnReport, view: GameView) -> None:
    if report.public_message:
        console.print(f"[cyan]Agent:[/cyan] {report.public_message}")
    if report.proposal_source == "fallback" and report.fallback_reason:
        console.print(
            f"[yellow]Fell back to a deterministic attack: {report.fallback_reason}[/yellow]"
        )
    console.print(
        f"[dim]agent {report.actor_id} — source: {report.proposal_source}, "
        f"attempts: {report.action_attempts}, llm calls: {len(report.invocations)}[/dim]"
    )
    render_report(console, report.turn_report, view)
```

3e. In the parser (after the `--db` line), add:

```python
    parser.add_argument(
        "--agent",
        choices=("off", "llm", "fake"),
        default="off",
        help="add an AI-controlled party member (off | llm | fake)",
    )
```

3f. Replace the setup block (lines 145–148) — Brix must join before `start_combat`:

```python
    game_id = service.create_game(CreateGameCommand(seed=args.seed))
    service.add_character(game_id, _fighter("Arin"))
    agent_service: AgentTurnService | None = None
    if args.agent != "off":
        try:
            agent_service = _wire_agent(service, game_id, args.agent, console)
        except (ValueError, ModelError) as error:
            console.print(f"[red]{error}[/red]")
            return 2
    service.add_character(game_id, _goblin())
    service.start_combat(game_id)
```

3g. In the main loop, insert this branch **between the enemy-turn branch's `continue` (current line 164) and the input prompt (`try:` at line 166)**:

```python
        if (
            agent_service is not None
            and view.combat is not None
            and view.combat.status == "active"
            and view.combat.active_actor_id is not None
            and agent_service.is_agent_controlled(CharacterId(view.combat.active_actor_id))
        ):
            try:
                agent_report = agent_service.take_turn(
                    GameId(view.game_id),
                    CharacterId(view.combat.active_actor_id),
                )
            except DomainError as error:
                console.print(f"[red]{error}[/red]")
                continue
            _render_agent_turn(console, agent_report, view)
            continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/interfaces/test_cli.py -q`
Expected: PASS (existing tests unchanged + 4 new)

- [ ] **Step 5: Quality gates + offline demo**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: all green — **279** offline tests pass. Manual check (no network): `.venv/bin/python -m interfaces.cli.app --agent fake --seed 42 < /dev/null` starts, prints the Brix announcement, and exits cleanly on EOF.

- [ ] **Step 6: Commit**

```bash
git add src/interfaces/cli/app.py tests/interfaces/test_cli.py
git commit -m "feat(interfaces): add --agent flag wiring the AI character into the CLI

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Purity test + README documentation

**Files:**
- Create: `tests/ai/agents/test_purity.py`
- Modify: `README.md`
- Test: `tests/ai/agents/test_purity.py`

**Interfaces:**
- Consumes: nothing (AST scan of the source tree).
- Produces: a structural guarantee that `src/ai/agents/` never imports `domain`, `application`, `interfaces`, or `infrastructure` (spec decision 3, completion checklist item 1).

- [ ] **Step 1: Write the failing test**

Create `tests/ai/agents/test_purity.py`:

```python
"""Purity test: src/ai/agents stays game-free (spec decision 3, CLAUDE.md §7)."""

import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "ai" / "agents"
_FORBIDDEN_ROOTS = {"domain", "application", "interfaces", "infrastructure"}


def test_ai_agents_package_never_imports_game_layers() -> None:
    offenders: list[str] = []
    for path in sorted(_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in _FORBIDDEN_ROOTS:
                    offenders.append(f"{path.name}: {name}")
    assert offenders == []
```

Note: Tasks 1–2 already wrote a pure package, so this test passes immediately — its value is that it fails the moment anyone adds a game import to `src/ai/agents/`. Verify it fails when it should: temporarily append `import application.views  # noqa` to `src/ai/agents/retry.py`, run the test (expect FAIL), revert the line.

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/ai/agents/test_purity.py -q`
Expected: PASS (1 passed)

- [ ] **Step 3: Update README.md**

3a. Replace the last sentence of the "Model gateway" section:

```markdown
Model profiles (`gm`, `player`, `cheap`, `reasoning`, `creative`, `embedding`)
are configured in `config/llm.toml`. Nothing in the game calls the gateway yet —
the first consumer is the character agent (Plan 4).
```

with:

```markdown
Model profiles (`gm`, `player`, `cheap`, `reasoning`, `creative`, `embedding`)
are configured in `config/llm.toml`. The first consumer is the AI character
agent (`--agent llm`).
```

3b. Append a new section:

````markdown
## AI character agent (offline by default)

`--agent llm` adds an AI-controlled party member (Brix) who decides her own
attacks through the model gateway; the human keeps commanding Arin:

```bash
export OPENROUTER_API_KEY=sk-or-...
.venv/bin/python -m interfaces.cli.app --agent llm --seed 42
```

An offline demo that never touches the network:

```bash
.venv/bin/python -m interfaces.cli.app --agent fake --seed 42
```

Agent identity, persona, and objective live in `config/agents.toml`; retry
budgets under `[agent]`. The agent proposes, the rules engine decides —
invalid proposals are retried with the rejection reason, then a deterministic
fallback attack.
````

- [ ] **Step 4: Verify spec completion checklist items**

Run: `git log master..HEAD --oneline -- src/domain`
Expected: empty output (domain untouched).

- [ ] **Step 5: Final quality gates**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: **280 passed + 1 skipped** without `OPENROUTER_API_KEY` (**281 passed** with it). New tests: 59 (T1 13, T2 6, T3 8, T4 8, T5 10, T6 9, T7 4, T8 1) on top of the 221-test offline baseline.

- [ ] **Step 6: Commit**

```bash
git add tests/ai/agents/test_purity.py README.md
git commit -m "test(ai): pin src/ai/agents as game-free; document the AI character agent

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Final verification (after Task 8)

- [ ] Full suite green offline: `.venv/bin/python -m pytest -q` → 280 passed + 1 skipped without `OPENROUTER_API_KEY` (281 passed with it).
- [ ] `git log master..HEAD --oneline -- src/domain` → empty (spec checklist: domain untouched).
- [ ] `--agent off` behavior unchanged: existing CLI tests untouched and passing.
- [ ] Enemy HP/AC structurally absent from agent perception (Task 4 pin) and never in any prompt (Task 5 `count("HP") == 1` / `count("AC") == 1` pins).
- [ ] Non-retryable errors propagate (`AgentRuntimeMisconfiguredError` re-raised before `AgentRuntimeError` in the service); both budgets bounded; fallback deterministic (`first_living_opponent`).
- [ ] No provider SDK outside `src/infrastructure/llm/`; no new dependencies (`git diff master --stat -- pyproject.toml uv.lock` shows no runtime-dependency change).
