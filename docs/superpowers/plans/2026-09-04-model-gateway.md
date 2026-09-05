# Model Gateway Implementation Plan (Plan 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the AI platform's provider-agnostic `ModelGateway` port with value types, a deterministic `FakeModelGateway`, a thin OpenRouter adapter (httpx, no provider SDK), and TOML-configured model profiles — no wiring into the game yet.

**Architecture:** The Protocol and value types live in `src/ai/models/` (AI platform boundary, provider-free and game-free). `src/infrastructure/llm/openrouter/` implements the port; nothing in `ai/` imports infrastructure. Schema enforcement is a stdlib JSON-Schema-subset validator shared by the fake and the adapter, so validation is identical offline and online. The gateway is single-attempt transport; retries belong to Plan 4.

**Tech Stack:** Python 3.12, stdlib (`dataclasses`, `typing`, `tomllib`, `json`, `uuid`, `time`), `httpx>=0.27` (new runtime dependency, adapter only), pytest with `asyncio.run()` in tests (no pytest-asyncio).

**Spec:** `docs/superpowers/specs/2026-09-04-model-gateway-design.md` — executors read both.

## Global Constraints

- All commands run via the project-local venv: `.venv/bin/python -m pytest`, `.venv/bin/python -m ruff`, `.venv/bin/python -m mypy`. Work in the repo root (or a superpowers worktree created at execution time).
- `mypy --strict` on `src/` (configured in `pyproject.toml`: `files = ["src"]`) must stay clean; `ruff check` (select E,F,I,UP,B; line-length 100) must stay clean.
- New runtime dependency allowed in this plan: `httpx>=0.27` ONLY. No pytest-asyncio — every async test wraps the call in `asyncio.run(...)`.
- `src/ai/` must not import from `infrastructure/`, `domain/`, `application/`, or `interfaces/`. OpenRouter names (endpoints, headers, key) appear ONLY under `src/infrastructure/llm/`.
- API key comes from the `OPENROUTER_API_KEY` environment variable only; never committed, never logged, never placed in `config/llm.toml`.
- All six model profiles use the cheap model `z-ai/glm-5.3-flash` (user directive, 2026-09-04); per-profile temperature stays.
- The gateway is single-attempt transport: no retry/backoff/fallback logic anywhere in this plan (Plan 4 owns retries). No `stream()`/`embed()` methods.
- No changes to `domain/`, `application/`, or existing `interfaces/` files.
- Imports follow ruff isort order: stdlib, third-party, then first-party (`ai.*`, `infrastructure.*`) — `pytest` runs with `pythonpath=["src"]` so first-party imports are top-level.
- Tests never need `__init__.py` files (matches existing `tests/` layout); test basenames must stay unique across directories.
- Every commit: conventional message scoped by layer, ending with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.

## File Structure

```text
src/ai/models/                     Task 1–4: the AI platform's model boundary
├── __init__.py                    docstring only (Task 1)
├── types.py                       Message, ModelRequest, Usage, LLMInvocation, ModelResponse, StructuredModelResponse
├── errors.py                      ModelError taxonomy + profile-config errors
├── gateway.py                     ModelGateway Protocol (async generate / generate_structured)
├── schema.py                      JSON-Schema-subset validator (Task 2)
├── profiles.py                    ModelProfile, ModelPricing, ModelProfileCatalog, load_model_profiles (Task 3)
└── fake.py                        FakeModelGateway (Task 4)

config/llm.toml                    Task 3: shipped profile config (no secrets)

src/infrastructure/llm/            Tasks 5–8: the provider side
├── __init__.py                    create_gateway factory (Task 8)
└── openrouter/
    ├── __init__.py                docstring only (Task 5)
    └── adapter.py                 OpenRouterModelGateway (Tasks 5–7)

tests/ai/models/                   Tasks 1–4 tests
tests/infrastructure/llm/          Tasks 5–8 tests
tests/integration/                 Task 9: opt-in live smoke test
```

---

### Task 1: Value types, error taxonomy, and the ModelGateway Protocol

**Files:**
- Create: `src/ai/models/__init__.py`
- Create: `src/ai/models/types.py`
- Create: `src/ai/models/errors.py`
- Create: `src/ai/models/gateway.py`
- Test: `tests/ai/models/test_types.py`

**Interfaces:**
- Consumes: nothing new (stdlib only).
- Produces: `Message(role, content)`, `ModelRequest(messages: tuple[Message, ...], model: str, temperature: float = 0.7, max_tokens: int | None = None, timeout_seconds: float = 60.0)`, `Usage(input_tokens, output_tokens)` with `.total_tokens`, `LLMInvocation(provider, model, operation, status, error_kind, latency_ms, input_tokens, output_tokens, estimated_cost_usd, request_id)`, `ModelResponse(text, model, usage, finish_reason, invocation)`, `StructuredModelResponse(data, model, usage, finish_reason, invocation)`; `ModelError(message, invocation=None)` base with `.invocation: LLMInvocation | None`; subclasses `ModelTimeoutError`, `ModelRateLimitedError` (`.retry_after_seconds: float | None`), `ModelRequestError`, `ModelUnavailableError`, `ModelInvalidResponseError`, `MissingAPIKeyError`, `UnsupportedSchemaError`, `ProfileConfigError`, `ProfileNotFoundError`, `InvalidProfileError`, `UnknownProviderError`; `ModelGateway` Protocol with `async generate(request) -> ModelResponse` and `async generate_structured(request, schema: Mapping[str, Any]) -> StructuredModelResponse`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ai/models/test_types.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from ai.models.errors import (
    InvalidProfileError,
    MissingAPIKeyError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    ProfileConfigError,
    ProfileNotFoundError,
    UnsupportedSchemaError,
    UnknownProviderError,
)
from ai.models.types import (
    LLMInvocation,
    Message,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)


def _invocation() -> LLMInvocation:
    return LLMInvocation(
        provider="fake",
        model="m",
        operation="generate",
        status="ok",
        error_kind=None,
        latency_ms=1,
        input_tokens=1,
        output_tokens=1,
        estimated_cost_usd=None,
        request_id="abc",
    )


def test_usage_total_tokens() -> None:
    assert Usage(input_tokens=11, output_tokens=7).total_tokens == 18


def test_model_request_defaults() -> None:
    request = ModelRequest(messages=(Message(role="user", content="hi"),), model="m")
    assert request.temperature == 0.7
    assert request.max_tokens is None
    assert request.timeout_seconds == 60.0


def test_message_is_frozen() -> None:
    message = Message(role="user", content="hello")
    with pytest.raises(FrozenInstanceError):
        message.content = "mutated"


def test_response_types_carry_invocation() -> None:
    invocation = _invocation()
    response = ModelResponse(
        text="ok", model="m", usage=Usage(1, 1), finish_reason="stop",
        invocation=invocation,
    )
    structured = StructuredModelResponse(
        data={"a": 1}, model="m", usage=Usage(1, 1), finish_reason="stop",
        invocation=invocation,
    )
    assert response.invocation is invocation
    assert structured.data == {"a": 1}


def test_model_error_stores_invocation() -> None:
    invocation = _invocation()
    error = ModelError("boom", invocation=invocation)
    assert error.invocation is invocation
    assert ModelError("bare").invocation is None


def test_rate_limited_error_carries_retry_after() -> None:
    error = ModelRateLimitedError("slow down", retry_after_seconds=7.0)
    assert error.retry_after_seconds == 7.0
    assert isinstance(error, ModelError)


def test_error_hierarchy() -> None:
    for cls in (
        ModelTimeoutError,
        ModelRateLimitedError,
        ModelRequestError,
        ModelUnavailableError,
        ModelInvalidResponseError,
        MissingAPIKeyError,
        UnsupportedSchemaError,
        ProfileConfigError,
        ProfileNotFoundError,
        InvalidProfileError,
        UnknownProviderError,
    ):
        assert issubclass(cls, ModelError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/models/test_types.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.models'`

- [ ] **Step 3: Write the implementation**

Create `src/ai/models/__init__.py`:

```python
"""AI platform model boundary: provider-free, game-free model gateway contracts."""
```

Create `src/ai/models/types.py`:

```python
"""Value types shared by every ModelGateway implementation."""

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[Message, ...]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class LLMInvocation:
    """Per-call telemetry metadata (CLAUDE.md §34). Never prompts, payloads, or reasoning."""

    provider: str
    model: str
    operation: str
    status: str
    error_kind: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    request_id: str


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str
    usage: Usage
    finish_reason: str
    invocation: LLMInvocation


@dataclass(frozen=True)
class StructuredModelResponse:
    data: dict[str, Any]
    model: str
    usage: Usage
    finish_reason: str
    invocation: LLMInvocation
```

Create `src/ai/models/errors.py`:

```python
"""Error taxonomy for the model gateway layer (extends CLAUDE.md §49)."""

from ai.models.types import LLMInvocation


class ModelError(Exception):
    """Base class for model-gateway failures; carries per-call telemetry."""

    def __init__(self, message: str, invocation: LLMInvocation | None = None) -> None:
        super().__init__(message)
        self.invocation = invocation


class ModelTimeoutError(ModelError):
    pass


class ModelRateLimitedError(ModelError):
    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        invocation: LLMInvocation | None = None,
    ) -> None:
        super().__init__(message, invocation)
        self.retry_after_seconds = retry_after_seconds


class ModelRequestError(ModelError):
    pass


class ModelUnavailableError(ModelError):
    pass


class ModelInvalidResponseError(ModelError):
    pass


class MissingAPIKeyError(ModelError):
    pass


class UnsupportedSchemaError(ModelError):
    pass


class ProfileConfigError(ModelError):
    pass


class ProfileNotFoundError(ModelError):
    pass


class InvalidProfileError(ModelError):
    pass


class UnknownProviderError(ModelError):
    pass
```

Create `src/ai/models/gateway.py`:

```python
"""ModelGateway port — the AI platform's provider-agnostic model boundary."""

from collections.abc import Mapping
from typing import Any, Protocol

from ai.models.types import ModelRequest, ModelResponse, StructuredModelResponse


class ModelGateway(Protocol):
    """Single-attempt transport (CLAUDE.md §23). Retries belong to the caller (§28)."""

    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/models/test_types.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Verify lint and types**

Run: `.venv/bin/python -m ruff check src/ai tests/ai && .venv/bin/python -m mypy src/ai`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/ai tests/ai/models/test_types.py
git commit -m "feat(ai): add model gateway value types, error taxonomy and protocol

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: JSON-Schema-subset validator

**Files:**
- Create: `src/ai/models/schema.py`
- Test: `tests/ai/models/test_schema.py`

**Interfaces:**
- Consumes: `ModelInvalidResponseError`, `UnsupportedSchemaError` from `ai.models.errors`.
- Produces: `validate_against_schema(data: Any, schema: Mapping[str, Any]) -> None` — raises `ModelInvalidResponseError` with path-precise messages (root path `data`, e.g. `data.parameters.target_id: expected string, got int`) or `UnsupportedSchemaError` for keywords outside the subset (`type` object/string/number/integer/boolean/array, `properties`, `required`, `additionalProperties: false`, `enum`, `items`, `minimum`, `maximum`).

- [ ] **Step 1: Write the failing tests**

Create `tests/ai/models/test_schema.py`:

```python
import pytest

from ai.models.errors import ModelInvalidResponseError, UnsupportedSchemaError
from ai.models.schema import validate_against_schema

_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["attack", "move"]},
        "parameters": {
            "type": "object",
            "properties": {"target_id": {"type": "string"}},
            "required": ["target_id"],
            "additionalProperties": False,
        },
        "count": {"type": "integer", "minimum": 1, "maximum": 10},
        "tags": {"type": "array", "items": {"type": "string"}},
        "verified": {"type": "boolean"},
        "ratio": {"type": "number"},
    },
    "required": ["action_type"],
    "additionalProperties": False,
}


def test_valid_object_passes() -> None:
    data = {
        "action_type": "attack",
        "parameters": {"target_id": "goblin-1"},
        "count": 3,
        "tags": ["melee"],
        "verified": True,
        "ratio": 0.5,
    }
    validate_against_schema(data, _OBJECT_SCHEMA)


def test_missing_required_field() -> None:
    with pytest.raises(ModelInvalidResponseError, match="action_type: required field is missing"):
        validate_against_schema({}, _OBJECT_SCHEMA)


def test_nested_path_in_error_message() -> None:
    data = {"action_type": "attack", "parameters": {"target_id": 3}}
    with pytest.raises(
        ModelInvalidResponseError, match="data.parameters.target_id: expected string, got int"
    ):
        validate_against_schema(data, _OBJECT_SCHEMA)


def test_enum_violation() -> None:
    with pytest.raises(ModelInvalidResponseError, match="is not one of"):
        validate_against_schema({"action_type": "flee"}, _OBJECT_SCHEMA)


def test_additional_properties_rejected() -> None:
    with pytest.raises(ModelInvalidResponseError, match="unexpected field"):
        validate_against_schema({"action_type": "attack", "extra": 1}, _OBJECT_SCHEMA)


def test_integer_bounds() -> None:
    with pytest.raises(ModelInvalidResponseError, match="less than minimum"):
        validate_against_schema({"action_type": "attack", "count": 0}, _OBJECT_SCHEMA)
    with pytest.raises(ModelInvalidResponseError, match="greater than maximum"):
        validate_against_schema({"action_type": "attack", "count": 11}, _OBJECT_SCHEMA)


def test_array_items_validated_with_index_path() -> None:
    data = {"action_type": "attack", "tags": ["ok", 5]}
    with pytest.raises(ModelInvalidResponseError, match=r"data\.tags\[1\]: expected string"):
        validate_against_schema(data, _OBJECT_SCHEMA)


def test_boolean_is_not_integer() -> None:
    with pytest.raises(ModelInvalidResponseError, match="expected integer, got bool"):
        validate_against_schema({"action_type": "attack", "count": True}, _OBJECT_SCHEMA)


def test_number_accepts_integer_value() -> None:
    validate_against_schema({"action_type": "attack", "ratio": 1}, _OBJECT_SCHEMA)


def test_unsupported_keyword_rejected() -> None:
    with pytest.raises(UnsupportedSchemaError, match="oneOf"):
        validate_against_schema({}, {"oneOf": []})


def test_unsupported_nested_keyword_rejected() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string", "pattern": "^a$"}}}
    with pytest.raises(UnsupportedSchemaError, match="pattern"):
        validate_against_schema({}, schema)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/models/test_schema.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.models.schema'`

- [ ] **Step 3: Write the implementation**

Create `src/ai/models/schema.py`:

```python
"""Minimal JSON-Schema-subset validator shared by the fake and provider adapters.

Supports exactly the keywords Plan 4's action-proposal schemas need. Anything
outside the subset raises UnsupportedSchemaError — loud, not silent (spec:
"Structured output, schema validator" section).
"""

from collections.abc import Mapping
from typing import Any

from ai.models.errors import ModelInvalidResponseError, UnsupportedSchemaError

_SUPPORTED_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "items",
    "minimum",
    "maximum",
}

_TYPE_CHECKS: dict[str, Any] = {
    "object": lambda d: isinstance(d, dict),
    "string": lambda d: isinstance(d, str),
    "number": lambda d: isinstance(d, (int, float)) and not isinstance(d, bool),
    "integer": lambda d: isinstance(d, int) and not isinstance(d, bool),
    "boolean": lambda d: isinstance(d, bool),
    "array": lambda d: isinstance(d, list),
}


def validate_against_schema(data: Any, schema: Mapping[str, Any]) -> None:
    """Validate data against the supported JSON-Schema subset.

    Raises ModelInvalidResponseError with a path-precise message, or
    UnsupportedSchemaError when the schema uses keywords outside the subset.
    """
    _reject_unsupported(schema)
    _validate(data, schema, "data")


def _reject_unsupported(schema: Mapping[str, Any]) -> None:
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise UnsupportedSchemaError(
            f"unsupported schema keywords: {', '.join(sorted(unknown))}"
        )
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for child in properties.values():
            if isinstance(child, Mapping):
                _reject_unsupported(child)
    items = schema.get("items")
    if isinstance(items, Mapping):
        _reject_unsupported(items)


def _validate(data: Any, schema: Mapping[str, Any], path: str) -> None:
    expected = schema.get("type")
    if expected is not None:
        _check_type(data, expected, path)
    if "enum" in schema:
        allowed = schema["enum"]
        if data not in allowed:
            raise ModelInvalidResponseError(f"{path}: {data!r} is not one of {allowed!r}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            raise ModelInvalidResponseError(
                f"{path}: {data} is less than minimum {schema['minimum']}"
            )
        if "maximum" in schema and data > schema["maximum"]:
            raise ModelInvalidResponseError(
                f"{path}: {data} is greater than maximum {schema['maximum']}"
            )
    if expected == "object" or "properties" in schema:
        _validate_object(data, schema, path)
    if expected == "array" or "items" in schema:
        _validate_array(data, schema, path)


def _check_type(data: Any, expected: str, path: str) -> None:
    check = _TYPE_CHECKS.get(expected)
    if check is None:
        raise UnsupportedSchemaError(f"unsupported schema type: {expected!r}")
    if not check(data):
        raise ModelInvalidResponseError(
            f"{path}: expected {expected}, got {type(data).__name__}"
        )


def _validate_object(data: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(data, dict):
        return  # type mismatch already reported by _check_type
    for name in schema.get("required", []):
        if name not in data:
            raise ModelInvalidResponseError(f"{path}.{name}: required field is missing")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extras = set(data) - set(properties)
        if extras:
            raise ModelInvalidResponseError(
                f"{path}: unexpected field(s) {', '.join(sorted(extras))}"
            )
    for name, value in data.items():
        if name in properties and isinstance(properties[name], Mapping):
            _validate(value, properties[name], f"{path}.{name}")


def _validate_array(data: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(data, list):
        return
    items = schema.get("items")
    if isinstance(items, Mapping):
        for index, value in enumerate(data):
            _validate(value, items, f"{path}[{index}]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/models/test_schema.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src/ai tests/ai && .venv/bin/python -m mypy src/ai && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 6: Commit**

```bash
git add src/ai/models/schema.py tests/ai/models/test_schema.py
git commit -m "feat(ai): add JSON-Schema-subset validator for structured output

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Model profiles loader and shipped config

**Files:**
- Create: `src/ai/models/profiles.py`
- Create: `config/llm.toml`
- Test: `tests/ai/models/test_profiles.py`

**Interfaces:**
- Consumes: `ModelRequest`, `Message` from `ai.models.types`; `ProfileConfigError`, `ProfileNotFoundError`, `InvalidProfileError` from `ai.models.errors`.
- Produces: `ModelProfile(name, provider, model, temperature=0.7, max_tokens=None)` with `to_request(messages: Sequence[Message]) -> ModelRequest`; `ModelPricing(input_per_million_usd: float, output_per_million_usd: float)`; `ModelProfileCatalog(default_provider: str, profiles: Mapping[str, ModelProfile], pricing: Mapping[str, ModelPricing])` with `.get(name) -> ModelProfile` (raises `ProfileNotFoundError`); `load_model_profiles(path: str | Path) -> ModelProfileCatalog` (raises `ProfileConfigError` for missing/unreadable file, `InvalidProfileError` for entries missing `provider`/`model`).

- [ ] **Step 1: Write the failing tests**

Create `tests/ai/models/test_profiles.py`:

```python
from pathlib import Path

import pytest

from ai.models.errors import InvalidProfileError, ProfileConfigError, ProfileNotFoundError
from ai.models.profiles import ModelPricing, load_model_profiles
from ai.models.types import Message

_MINIMAL_TOML = """\
default_provider = "openrouter"

[profiles.gm]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.8
max_tokens = 1024

[profiles.cheap]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"

[pricing."z-ai/glm-5.3-flash"]
input_per_million_usd = 0.07125
output_per_million_usd = 0.2375
"""


def _write(tmp_path: Path, content: str) -> Path:
    config = tmp_path / "llm.toml"
    config.write_text(content, encoding="utf-8")
    return config


def test_loads_profiles_and_pricing(tmp_path: Path) -> None:
    catalog = load_model_profiles(_write(tmp_path, _MINIMAL_TOML))

    assert catalog.default_provider == "openrouter"
    gm = catalog.get("gm")
    assert gm.model == "z-ai/glm-5.3-flash"
    assert gm.temperature == 0.8
    assert gm.max_tokens == 1024

    cheap = catalog.get("cheap")
    assert cheap.temperature == 0.7
    assert cheap.max_tokens is None

    assert catalog.pricing["z-ai/glm-5.3-flash"] == ModelPricing(
        input_per_million_usd=0.07125, output_per_million_usd=0.2375
    )


def test_unknown_profile_raises(tmp_path: Path) -> None:
    catalog = load_model_profiles(_write(tmp_path, _MINIMAL_TOML))
    with pytest.raises(ProfileNotFoundError, match="nope"):
        catalog.get("nope")


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProfileConfigError):
        load_model_profiles(tmp_path / "absent.toml")


def test_profile_missing_model_raises(tmp_path: Path) -> None:
    config = _write(tmp_path, '[profiles.gm]\nprovider = "openrouter"\n')
    with pytest.raises(InvalidProfileError, match="gm"):
        load_model_profiles(config)


def test_to_request_builds_model_request(tmp_path: Path) -> None:
    catalog = load_model_profiles(_write(tmp_path, _MINIMAL_TOML))
    request = catalog.get("gm").to_request([Message(role="user", content="hi")])
    assert request.model == "z-ai/glm-5.3-flash"
    assert request.messages == (Message(role="user", content="hi"),)
    assert request.temperature == 0.8
    assert request.max_tokens == 1024


def test_shipped_config_has_six_cheap_profiles() -> None:
    config = Path(__file__).parents[3] / "config" / "llm.toml"
    catalog = load_model_profiles(config)
    assert catalog.default_provider == "openrouter"
    assert set(catalog.profiles) == {
        "gm",
        "player",
        "cheap",
        "reasoning",
        "creative",
        "embedding",
    }
    for profile in catalog.profiles.values():
        assert profile.model == "z-ai/glm-5.3-flash"
    assert set(catalog.pricing) == {"z-ai/glm-5.3-flash", "z-ai/glm-5.2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/models/test_profiles.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.models.profiles'`

- [ ] **Step 3: Write the implementation**

Create `src/ai/models/profiles.py`:

```python
"""Model profiles: named model configurations loaded from TOML (stdlib tomllib)."""

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai.models.errors import InvalidProfileError, ProfileConfigError, ProfileNotFoundError
from ai.models.types import Message, ModelRequest


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None

    def to_request(self, messages: Sequence[Message]) -> ModelRequest:
        return ModelRequest(
            messages=tuple(messages),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float
    output_per_million_usd: float


@dataclass
class ModelProfileCatalog:
    default_provider: str
    profiles: Mapping[str, ModelProfile]
    pricing: Mapping[str, ModelPricing]

    def get(self, name: str) -> ModelProfile:
        try:
            return self.profiles[name]
        except KeyError:
            raise ProfileNotFoundError(f"unknown model profile: {name!r}") from None


def load_model_profiles(path: str | Path) -> ModelProfileCatalog:
    """Load profiles and pricing from a TOML file (structure validation only)."""
    file = Path(path)
    if not file.is_file():
        raise ProfileConfigError(f"model profile config not found: {file}")
    try:
        raw = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProfileConfigError(f"invalid TOML in {file}: {exc}") from exc

    profiles: dict[str, ModelProfile] = {}
    for name, entry in raw.get("profiles", {}).items():
        if not isinstance(entry, Mapping) or "provider" not in entry or "model" not in entry:
            raise InvalidProfileError(f"profile {name!r} must define provider and model")
        max_tokens = entry.get("max_tokens")
        profiles[name] = ModelProfile(
            name=name,
            provider=str(entry["provider"]),
            model=str(entry["model"]),
            temperature=float(entry.get("temperature", 0.7)),
            max_tokens=int(max_tokens) if max_tokens is not None else None,
        )

    pricing: dict[str, ModelPricing] = {}
    for model_id, entry in raw.get("pricing", {}).items():
        required = ("input_per_million_usd", "output_per_million_usd")
        if not isinstance(entry, Mapping) or any(key not in entry for key in required):
            raise InvalidProfileError(
                f"pricing for {model_id!r} must define input and output per-million USD"
            )
        pricing[model_id] = ModelPricing(
            input_per_million_usd=float(entry["input_per_million_usd"]),
            output_per_million_usd=float(entry["output_per_million_usd"]),
        )

    return ModelProfileCatalog(
        default_provider=str(raw.get("default_provider", "openrouter")),
        profiles=profiles,
        pricing=pricing,
    )
```

Create `config/llm.toml`:

```toml
# Model profiles for the Agentic Conclave model gateway (Plan 3).
# No secrets here: the OpenRouter key comes from the OPENROUTER_API_KEY env var.
# Until the final version, ALL profiles use the cheap model (user directive,
# 2026-09-04); upgrading a profile is a one-line config edit.

default_provider = "openrouter"

[profiles.gm]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.8
max_tokens = 1024

[profiles.player]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.7
max_tokens = 1024

[profiles.cheap]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.5
max_tokens = 512

[profiles.reasoning]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.3

[profiles.creative]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 1.0

[profiles.embedding]  # reserved — unused until Plan 7 (pgvector memory)
provider = "openrouter"
model = "z-ai/glm-5.3-flash"

[pricing."z-ai/glm-5.3-flash"]  # verified 2026-09-04; USD per million tokens
input_per_million_usd = 0.07125
output_per_million_usd = 0.2375

[pricing."z-ai/glm-5.2"]  # kept for the future upgrade path
input_per_million_usd = 0.4875
output_per_million_usd = 1.56
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/models/test_profiles.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src/ai tests/ai && .venv/bin/python -m mypy src/ai && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 6: Commit**

```bash
git add src/ai/models/profiles.py config/llm.toml tests/ai/models/test_profiles.py
git commit -m "feat(ai): add model profile loader and shipped llm.toml config

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: FakeModelGateway

**Files:**
- Create: `src/ai/models/fake.py`
- Test: `tests/ai/models/test_fake.py`

**Interfaces:**
- Consumes: `validate_against_schema(data, schema)` from `ai.models.schema`; types and errors from Tasks 1–2.
- Produces: `FakeModelGateway()` with `enqueue_text(text: str)`, `enqueue_structured(data: dict[str, Any])`, `enqueue_error(error: ModelError)`, `invocations: list[LLMInvocation]`; plus fake-only exceptions `FakeGatewayExhaustedError` (empty queue) and `FakeGatewayScriptError` (scripted kind mismatches the call — a compatible extension of the spec's fake-only error set). Deterministic constants: usage `Usage(10, 5)`, `finish_reason="stop"`, `latency_ms=0`, `provider="fake"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ai/models/test_fake.py`:

```python
import asyncio

import pytest

from ai.models.errors import ModelInvalidResponseError, ModelTimeoutError
from ai.models.fake import FakeGatewayExhaustedError, FakeGatewayScriptError, FakeModelGateway
from ai.models.types import Message, ModelRequest

_ACTION_SCHEMA = {
    "type": "object",
    "properties": {"action_type": {"type": "string"}},
    "required": ["action_type"],
    "additionalProperties": False,
}


def _request() -> ModelRequest:
    return ModelRequest(
        messages=(Message(role="user", content="decide"),), model="test-model"
    )


def test_serves_scripted_text_in_order() -> None:
    fake = FakeModelGateway()
    fake.enqueue_text("first")
    fake.enqueue_text("second")

    first = asyncio.run(fake.generate(_request()))
    second = asyncio.run(fake.generate(_request()))

    assert (first.text, second.text) == ("first", "second")
    assert first.finish_reason == "stop"
    assert first.model == "test-model"
    assert first.usage.total_tokens == 15
    assert first.invocation.provider == "fake"
    assert first.invocation.status == "ok"
    assert len(fake.invocations) == 2


def test_serves_structured_payload() -> None:
    fake = FakeModelGateway()
    fake.enqueue_structured({"action_type": "attack"})

    response = asyncio.run(fake.generate_structured(_request(), _ACTION_SCHEMA))

    assert response.data == {"action_type": "attack"}
    assert response.invocation.provider == "fake"
    assert response.invocation.operation == "generate_structured"


def test_rejects_invalid_scripted_payload() -> None:
    fake = FakeModelGateway()
    fake.enqueue_structured({"action_type": 3})

    with pytest.raises(ModelInvalidResponseError) as excinfo:
        asyncio.run(fake.generate_structured(_request(), _ACTION_SCHEMA))

    assert "action_type" in str(excinfo.value)
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "invalid_response"
    assert fake.invocations[-1].status == "error"


def test_empty_queue_raises() -> None:
    fake = FakeModelGateway()
    with pytest.raises(FakeGatewayExhaustedError):
        asyncio.run(fake.generate(_request()))


def test_kind_mismatch_does_not_consume_queue() -> None:
    fake = FakeModelGateway()
    fake.enqueue_text("hello")

    with pytest.raises(FakeGatewayScriptError):
        asyncio.run(fake.generate_structured(_request(), _ACTION_SCHEMA))

    response = asyncio.run(fake.generate(_request()))
    assert response.text == "hello"


def test_error_injection_attaches_invocation() -> None:
    fake = FakeModelGateway()
    fake.enqueue_error(ModelTimeoutError("slow"))

    with pytest.raises(ModelTimeoutError) as excinfo:
        asyncio.run(fake.generate(_request()))

    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.status == "timeout"
    assert fake.invocations[-1].status == "timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/models/test_fake.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.models.fake'`

- [ ] **Step 3: Write the implementation**

Create `src/ai/models/fake.py`:

```python
"""Deterministic, scriptable ModelGateway for tests and offline runs (Phase 10)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from ai.models.errors import ModelError, ModelInvalidResponseError, ModelTimeoutError
from ai.models.schema import validate_against_schema
from ai.models.types import (
    LLMInvocation,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)

_FAKE_USAGE = Usage(input_tokens=10, output_tokens=5)


class FakeGatewayExhaustedError(Exception):
    """Raised when a test makes more gateway calls than it scripted."""


class FakeGatewayScriptError(Exception):
    """Raised when the scripted response kind does not match the call."""


@dataclass
class _Entry:
    kind: str  # "text" | "structured" | "error"
    text: str | None = None
    data: dict[str, Any] | None = None
    error: ModelError | None = None


class FakeModelGateway:
    """Serves scripted responses in order; records every LLMInvocation."""

    def __init__(self) -> None:
        self._queue: list[_Entry] = []
        self.invocations: list[LLMInvocation] = []

    def enqueue_text(self, text: str) -> None:
        self._queue.append(_Entry(kind="text", text=text))

    def enqueue_structured(self, data: dict[str, Any]) -> None:
        self._queue.append(_Entry(kind="structured", data=data))

    def enqueue_error(self, error: ModelError) -> None:
        self._queue.append(_Entry(kind="error", error=error))

    async def generate(self, request: ModelRequest) -> ModelResponse:
        entry = self._next("text")
        if entry.error is not None:
            self._raise(request, "generate", entry.error)
        assert entry.text is not None
        invocation = self._record(request, "generate")
        return ModelResponse(
            text=entry.text,
            model=request.model,
            usage=_FAKE_USAGE,
            finish_reason="stop",
            invocation=invocation,
        )

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        entry = self._next("structured")
        if entry.error is not None:
            self._raise(request, "generate_structured", entry.error)
        assert entry.data is not None
        try:
            validate_against_schema(entry.data, schema)
        except ModelInvalidResponseError as exc:
            invocation = self._failed(request, "generate_structured", "invalid_response")
            raise ModelInvalidResponseError(str(exc), invocation=invocation) from exc
        invocation = self._record(request, "generate_structured")
        return StructuredModelResponse(
            data=entry.data,
            model=request.model,
            usage=_FAKE_USAGE,
            finish_reason="stop",
            invocation=invocation,
        )

    def _next(self, expected: str) -> _Entry:
        if not self._queue:
            raise FakeGatewayExhaustedError("FakeModelGateway has no scripted responses left")
        entry = self._queue[0]
        if entry.error is None and entry.kind != expected:
            raise FakeGatewayScriptError(
                f"next scripted response is {entry.kind!r}, but the call expected {expected!r}"
            )
        return self._queue.pop(0)

    def _raise(
        self, request: ModelRequest, operation: str, error: ModelError
    ) -> NoReturn:
        status = "timeout" if isinstance(error, ModelTimeoutError) else "error"
        error.invocation = LLMInvocation(
            provider="fake",
            model=request.model,
            operation=operation,
            status=status,
            error_kind=status,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        self.invocations.append(error.invocation)
        raise error

    def _record(self, request: ModelRequest, operation: str) -> LLMInvocation:
        invocation = LLMInvocation(
            provider="fake",
            model=request.model,
            operation=operation,
            status="ok",
            error_kind=None,
            latency_ms=0,
            input_tokens=_FAKE_USAGE.input_tokens,
            output_tokens=_FAKE_USAGE.output_tokens,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        self.invocations.append(invocation)
        return invocation

    def _failed(
        self, request: ModelRequest, operation: str, error_kind: str
    ) -> LLMInvocation:
        invocation = LLMInvocation(
            provider="fake",
            model=request.model,
            operation=operation,
            status="error",
            error_kind=error_kind,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        self.invocations.append(invocation)
        return invocation
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/models/test_fake.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src/ai tests/ai && .venv/bin/python -m mypy src/ai && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 6: Commit**

```bash
git add src/ai/models/fake.py tests/ai/models/test_fake.py
git commit -m "feat(ai): add deterministic scriptable FakeModelGateway

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: OpenRouter adapter — construction and generate happy path

**Files:**
- Create: `src/infrastructure/llm/__init__.py` (docstring only)
- Create: `src/infrastructure/llm/openrouter/__init__.py` (docstring only)
- Create: `src/infrastructure/llm/openrouter/adapter.py`
- Modify: `pyproject.toml` (add `httpx>=0.27` to `dependencies`)
- Test: `tests/infrastructure/llm/test_openrouter_adapter.py`

**Interfaces:**
- Consumes: `ModelRequest`, `ModelResponse`, `LLMInvocation`, `Usage` from `ai.models.types`; `MissingAPIKeyError` from `ai.models.errors`; `ModelPricing` from `ai.models.profiles`.
- Produces: `OpenRouterModelGateway(api_key: str, *, base_url: str = "https://openrouter.ai/api/v1", client: httpx.AsyncClient | None = None, pricing: Mapping[str, ModelPricing] | None = None, app_url: str | None = None, app_title: str | None = None)` with `async generate(request) -> ModelResponse` (Task 7 completes `generate_structured`). Empty key → `MissingAPIKeyError` at construction. Injected `client` enables `httpx.MockTransport` tests; when absent, a fresh per-call `httpx.AsyncClient` is used. Success-path mapping: `choices[0].message.content`, `usage.prompt_tokens`/`completion_tokens`, `model` echo, finish-reason neutral subset (`stop`/`length`/`content_filter`; unknown passes through verbatim; missing → `"error"`), cost from `pricing` keyed by model id (`None` when absent).

- [ ] **Step 1: Add the httpx dependency**

Edit `pyproject.toml` — in `[project] dependencies` add one line:

```toml
dependencies = [
    "rich>=13.7",
    "psycopg[binary]>=3.2",
    "httpx>=0.27",
]
```

Then install into the project venv:

```bash
uv pip install --python .venv/bin/python -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/infrastructure/llm/test_openrouter_adapter.py`:

```python
import asyncio
import json

import httpx
import pytest

from ai.models.errors import MissingAPIKeyError
from ai.models.profiles import ModelPricing
from ai.models.types import Message, ModelRequest
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_SUCCESS_BODY = {
    "id": "resp-1",
    "model": "z-ai/glm-5.3-flash",
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
        "model": "z-ai/glm-5.3-flash",
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def _gateway(handler, **kwargs) -> OpenRouterModelGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenRouterModelGateway("test-key", client=client, **kwargs)


def test_generate_maps_success_response() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request(temperature=0.4)))

    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "z-ai/glm-5.3-flash"
    assert captured["body"]["temperature"] == 0.4
    assert captured["body"]["messages"][0] == {"role": "user", "content": "decide"}
    assert "response_format" not in captured["body"]

    assert response.text == "I will strike the goblin."
    assert response.model == "z-ai/glm-5.3-flash"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (11, 7)
    assert response.finish_reason == "stop"
    assert response.invocation.provider == "openrouter"
    assert response.invocation.status == "ok"
    assert response.invocation.operation == "generate"
    assert response.invocation.estimated_cost_usd is None
    assert response.invocation.request_id


def test_generate_computes_cost_from_pricing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SUCCESS_BODY)

    pricing = {"z-ai/glm-5.3-flash": ModelPricing(0.07125, 0.2375)}
    gateway = _gateway(handler, pricing=pricing)
    response = asyncio.run(gateway.generate(_request()))
    expected = 11 / 1_000_000 * 0.07125 + 7 / 1_000_000 * 0.2375
    assert response.invocation.estimated_cost_usd == pytest.approx(expected)


def test_unknown_finish_reason_passes_through() -> None:
    body = {
        **_SUCCESS_BODY,
        "choices": [{**_SUCCESS_BODY["choices"][0], "finish_reason": "weird_reason"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request()))
    assert response.finish_reason == "weird_reason"


def test_missing_finish_reason_maps_to_error() -> None:
    body = {**_SUCCESS_BODY, "choices": [{"message": {"role": "assistant", "content": "x"}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate(_request()))
    assert response.finish_reason == "error"


def test_empty_api_key_rejected_at_construction() -> None:
    with pytest.raises(MissingAPIKeyError):
        OpenRouterModelGateway("")


def test_timeout_seconds_propagates_to_request() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json=_SUCCESS_BODY)

    gateway = _gateway(handler)
    asyncio.run(gateway.generate(_request(timeout_seconds=1.5)))
    assert captured["timeout"]["read"] == 1.5
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_adapter.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.llm'`

- [ ] **Step 4: Write the implementation**

Create `src/infrastructure/llm/__init__.py`:

```python
"""Provider-side model gateway implementations (CLAUDE.md §8, §24)."""
```

Create `src/infrastructure/llm/openrouter/__init__.py`:

```python
"""OpenRouter adapter — the only OpenRouter-aware package in the codebase."""
```

Create `src/infrastructure/llm/openrouter/adapter.py`:

```python
"""OpenRouter adapter: single-attempt ModelGateway over the OpenAI-compatible API."""

import json
import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx

from ai.models.errors import MissingAPIKeyError, ModelInvalidResponseError
from ai.models.profiles import ModelPricing
from ai.models.types import (
    LLMInvocation,
    ModelRequest,
    ModelResponse,
    StructuredModelResponse,
    Usage,
)

_FINISH_REASONS = {"stop", "length", "content_filter"}


class OpenRouterModelGateway:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.AsyncClient | None = None,
        pricing: Mapping[str, ModelPricing] | None = None,
        app_url: str | None = None,
        app_title: str | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("OpenRouter API key is empty; set OPENROUTER_API_KEY")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._pricing = dict(pricing) if pricing is not None else {}
        self._app_url = app_url
        self._app_title = app_title

    async def generate(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        body, content = await self._execute(request, "generate")
        usage = self._usage(body)
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider="openrouter",
            model=model,
            operation="generate",
            status="ok",
            error_kind=None,
            latency_ms=self._latency_ms(started),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=self._cost(model, usage),
            request_id=request_id,
        )
        return ModelResponse(
            text=content,
            model=model,
            usage=usage,
            finish_reason=self._finish_reason(body),
            invocation=invocation,
        )

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        raise NotImplementedError("structured output lands in a later task")

    async def _execute(
        self, request: ModelRequest, operation: str
    ) -> tuple[dict[str, Any], str]:
        payload = self._payload(request, operation)
        response = await self._post(request, payload)
        body = self._body(response)
        return body, self._content(body)

    def _payload(self, request: ModelRequest, operation: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if operation == "generate_structured":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _post(
        self, request: ModelRequest, payload: dict[str, Any]
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._app_url is not None:
            headers["HTTP-Referer"] = self._app_url
        if self._app_title is not None:
            headers["X-Title"] = self._app_title
        timeout = httpx.Timeout(request.timeout_seconds)
        url = f"{self._base_url}/chat/completions"
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient() as client:
            return await client.post(url, json=payload, headers=headers, timeout=timeout)

    def _body(self, response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()  # interim: replaced by error mapping in a later task
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelInvalidResponseError("OpenRouter returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise ModelInvalidResponseError("OpenRouter returned an unexpected JSON body")
        return body

    @staticmethod
    def _content(body: dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            raise ModelInvalidResponseError("OpenRouter returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content:
            raise ModelInvalidResponseError("OpenRouter returned empty message content")
        return content

    @staticmethod
    def _usage(body: dict[str, Any]) -> Usage:
        usage = body.get("usage") or {}
        return Usage(
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    @staticmethod
    def _finish_reason(body: dict[str, Any]) -> str:
        choices = body.get("choices") or []
        raw = choices[0].get("finish_reason") if choices else None
        if raw is None:
            return "error"
        return raw if raw in _FINISH_REASONS else str(raw)

    def _cost(self, model: str, usage: Usage) -> float | None:
        pricing = self._pricing.get(model)
        if pricing is None:
            return None
        return (
            usage.input_tokens / 1_000_000 * pricing.input_per_million_usd
            + usage.output_tokens / 1_000_000 * pricing.output_per_million_usd
        )

    @staticmethod
    def _latency_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_adapter.py -q`
Expected: PASS (6 tests)

- [ ] **Step 6: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/infrastructure/llm tests/infrastructure/llm
git commit -m "feat(infrastructure): add OpenRouter adapter generate capability

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: OpenRouter adapter — error mapping

**Files:**
- Modify: `src/infrastructure/llm/openrouter/adapter.py`
- Test: `tests/infrastructure/llm/test_openrouter_adapter.py` (extend)

**Interfaces:**
- Consumes: error taxonomy from Task 1 (`ModelError` with `.invocation`, `ModelTimeoutError`, `ModelRateLimitedError`, `ModelRequestError`, `ModelUnavailableError`, `ModelInvalidResponseError`).
- Produces: complete failure semantics of the adapter — no raw `httpx` exception ever escapes. Mapping: `httpx.TimeoutException` → `ModelTimeoutError`; HTTP 429 → `ModelRateLimitedError` (`.retry_after_seconds` from the `Retry-After` header, `None` when absent/unparseable); other 4xx → `ModelRequestError`; 5xx → `ModelUnavailableError`; other → `ModelError`; non-JSON 200 body / no choices / empty content → `ModelInvalidResponseError`. Every raised `ModelError` carries `.invocation` with `status="error"` (`"timeout"` for timeouts), `error_kind` in {`timeout`, `rate_limited`, `bad_request`, `unavailable`, `invalid_response`, `error`}, and measured `latency_ms`.

- [ ] **Step 1: Write the failing tests**

Append the following test functions to `tests/infrastructure/llm/test_openrouter_adapter.py`, and merge the new names into the existing top-of-file import (do NOT add a second import block mid-file — ruff E402):

```python
from ai.models.errors import (
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)


def test_timeout_maps_to_model_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    gateway = _gateway(handler)
    with pytest.raises(ModelTimeoutError) as excinfo:
        asyncio.run(gateway.generate(_request()))
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.status == "timeout"
    assert excinfo.value.invocation.error_kind == "timeout"


def test_429_maps_to_rate_limited_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "7"})

    gateway = _gateway(handler)
    with pytest.raises(ModelRateLimitedError) as excinfo:
        asyncio.run(gateway.generate(_request()))
    assert excinfo.value.retry_after_seconds == 7.0
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "rate_limited"


def test_429_without_parseable_retry_after_is_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    gateway = _gateway(handler)
    with pytest.raises(ModelRateLimitedError) as excinfo:
        asyncio.run(gateway.generate(_request()))
    assert excinfo.value.retry_after_seconds is None


def test_4xx_maps_to_model_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    gateway = _gateway(handler)
    with pytest.raises(ModelRequestError) as excinfo:
        asyncio.run(gateway.generate(_request()))
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "bad_request"


def test_5xx_maps_to_model_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    gateway = _gateway(handler)
    with pytest.raises(ModelUnavailableError):
        asyncio.run(gateway.generate(_request()))


def test_no_choices_maps_to_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    gateway = _gateway(handler)
    with pytest.raises(ModelInvalidResponseError) as excinfo:
        asyncio.run(gateway.generate(_request()))
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "invalid_response"


def test_empty_content_maps_to_invalid_response() -> None:
    body = {**_SUCCESS_BODY, "choices": [{"message": {"role": "assistant", "content": ""}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    gateway = _gateway(handler)
    with pytest.raises(ModelInvalidResponseError):
        asyncio.run(gateway.generate(_request()))


def test_non_json_body_maps_to_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    gateway = _gateway(handler)
    with pytest.raises(ModelInvalidResponseError):
        asyncio.run(gateway.generate(_request()))


def test_transport_error_maps_to_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    gateway = _gateway(handler)
    with pytest.raises(ModelError) as excinfo:
        asyncio.run(gateway.generate(_request()))
    assert not isinstance(excinfo.value, ModelTimeoutError)
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_adapter.py -q`
Expected: the 9 new tests FAIL (raw `httpx` exceptions escape or `raise_for_status` raises `httpx.HTTPStatusError`), the 6 Task-5 tests still PASS

- [ ] **Step 3: Implement the error mapping**

In `src/infrastructure/llm/openrouter/adapter.py`:

1. Extend the errors import:

```python
from ai.models.errors import (
    MissingAPIKeyError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)
```

2. Replace the body of `_execute` with timeout/transport mapping:

```python
    async def _execute(
        self, request: ModelRequest, operation: str
    ) -> tuple[dict[str, Any], str]:
        payload = self._payload(request, operation)
        try:
            response = await self._post(request, payload)
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"OpenRouter transport error: {exc}") from exc
        body = self._body(response)
        return body, self._content(body)
```

3. Replace `_body` with status-code mapping (drop `raise_for_status`):

```python
    def _body(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise ModelRateLimitedError(
                "OpenRouter rate limit hit (HTTP 429)",
                retry_after_seconds=self._retry_after(response),
            )
        if 400 <= response.status_code < 500:
            raise ModelRequestError(
                f"OpenRouter rejected the request (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )
        if response.status_code >= 500:
            raise ModelUnavailableError(
                f"OpenRouter unavailable (HTTP {response.status_code})"
            )
        if response.status_code != 200:
            raise ModelError(
                f"OpenRouter returned unexpected status HTTP {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelInvalidResponseError("OpenRouter returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise ModelInvalidResponseError("OpenRouter returned an unexpected JSON body")
        return body

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
```

4. Add invocation attachment. In both `generate` and (in Task 7) `generate_structured`, wrap the `_execute` call:

```python
        try:
            body, content = await self._execute(request, "generate")
        except ModelError as exc:
            raise self._with_invocation(
                request, "generate", started, request_id, exc
            ) from exc
```

and add the helpers:

```python
    def _with_invocation(
        self,
        request: ModelRequest,
        operation: str,
        started: float,
        request_id: str,
        exc: ModelError,
    ) -> ModelError:
        status = "timeout" if isinstance(exc, ModelTimeoutError) else "error"
        exc.invocation = LLMInvocation(
            provider="openrouter",
            model=request.model,
            operation=operation,
            status=status,
            error_kind=_error_kind(exc),
            latency_ms=self._latency_ms(started),
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=request_id,
        )
        return exc
```

plus a module-level function after `_FINISH_REASONS`:

```python
def _error_kind(exc: ModelError) -> str:
    if isinstance(exc, ModelTimeoutError):
        return "timeout"
    if isinstance(exc, ModelRateLimitedError):
        return "rate_limited"
    if isinstance(exc, ModelRequestError):
        return "bad_request"
    if isinstance(exc, ModelUnavailableError):
        return "unavailable"
    if isinstance(exc, ModelInvalidResponseError):
        return "invalid_response"
    return "error"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_adapter.py -q`
Expected: PASS (15 tests)

- [ ] **Step 5: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/llm/openrouter/adapter.py tests/infrastructure/llm/test_openrouter_adapter.py
git commit -m "feat(infrastructure): map provider failures to model gateway errors

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: OpenRouter adapter — structured output

**Files:**
- Modify: `src/infrastructure/llm/openrouter/adapter.py`
- Test: `tests/infrastructure/llm/test_openrouter_adapter.py` (extend)

**Interfaces:**
- Consumes: `validate_against_schema(data, schema)` from `ai.models.schema` (Task 2); everything from Tasks 5–6.
- Produces: working `async generate_structured(request, schema) -> StructuredModelResponse` — sends `response_format: {"type": "json_object"}`, parses the content as JSON (non-JSON → `ModelInvalidResponseError` with invocation), rejects non-object JSON, validates against the schema via the shared validator, returns `StructuredModelResponse(data, model, usage, finish_reason, invocation)` with cost populated. `generate_structured` failures carry `.invocation` exactly like `generate` failures.

- [ ] **Step 1: Write the failing tests**

Append to `tests/infrastructure/llm/test_openrouter_adapter.py`:

```python
_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string"},
        "parameters": {
            "type": "object",
            "properties": {"target_id": {"type": "string"}},
            "required": ["target_id"],
        },
    },
    "required": ["action_type", "parameters"],
}


def _structured_body(content: str) -> dict:
    return {
        **_SUCCESS_BODY,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def test_generate_structured_success() -> None:
    captured = {}
    payload = {"action_type": "attack", "parameters": {"target_id": "goblin-1"}}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_structured_body(json.dumps(payload)))

    gateway = _gateway(handler)
    response = asyncio.run(gateway.generate_structured(_request(), _ACTION_SCHEMA))

    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert response.data == payload
    assert response.model == "z-ai/glm-5.3-flash"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (11, 7)
    assert response.invocation.provider == "openrouter"
    assert response.invocation.operation == "generate_structured"
    assert response.invocation.status == "ok"


def test_generate_structured_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_structured_body("not json at all"))

    gateway = _gateway(handler)
    with pytest.raises(ModelInvalidResponseError) as excinfo:
        asyncio.run(gateway.generate_structured(_request(), _ACTION_SCHEMA))
    assert excinfo.value.invocation is not None
    assert excinfo.value.invocation.error_kind == "invalid_response"


def test_generate_structured_non_object_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_structured_body("[1, 2, 3]"))

    gateway = _gateway(handler)
    with pytest.raises(ModelInvalidResponseError, match="not a JSON object"):
        asyncio.run(gateway.generate_structured(_request(), _ACTION_SCHEMA))


def test_generate_structured_schema_violation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_structured_body(json.dumps({"action_type": 3})))

    gateway = _gateway(handler)
    with pytest.raises(ModelInvalidResponseError, match="action_type"):
        asyncio.run(gateway.generate_structured(_request(), _ACTION_SCHEMA))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_adapter.py -q`
Expected: the 4 new tests FAIL with `NotImplementedError`, the 15 earlier tests still PASS

- [ ] **Step 3: Implement generate_structured**

In `src/infrastructure/llm/openrouter/adapter.py`, add `validate_against_schema` to the imports:

```python
from ai.models.schema import validate_against_schema
```

Replace the `NotImplementedError` stub with:

```python
    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        try:
            body, content = await self._execute(request, "generate_structured")
            data = self._structured_data(content, schema)
        except ModelError as exc:
            raise self._with_invocation(
                request, "generate_structured", started, request_id, exc
            ) from exc
        usage = self._usage(body)
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider="openrouter",
            model=model,
            operation="generate_structured",
            status="ok",
            error_kind=None,
            latency_ms=self._latency_ms(started),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=self._cost(model, usage),
            request_id=request_id,
        )
        return StructuredModelResponse(
            data=data,
            model=model,
            usage=usage,
            finish_reason=self._finish_reason(body),
            invocation=invocation,
        )

    @staticmethod
    def _structured_data(content: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelInvalidResponseError(
                f"structured output is not valid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ModelInvalidResponseError("structured output is not a JSON object")
        validate_against_schema(parsed, schema)
        return parsed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_adapter.py -q`
Expected: PASS (19 tests)

- [ ] **Step 5: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/llm/openrouter/adapter.py tests/infrastructure/llm/test_openrouter_adapter.py
git commit -m "feat(infrastructure): add structured output support to OpenRouter adapter

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Provider factory

**Files:**
- Modify: `src/infrastructure/llm/__init__.py`
- Test: `tests/infrastructure/llm/test_factory.py`

**Interfaces:**
- Consumes: `OpenRouterModelGateway` (Task 5–7); `UnknownProviderError` from `ai.models.errors`; `ModelPricing` from `ai.models.profiles`.
- Produces: `create_gateway(provider: str, *, api_key: str, pricing: Mapping[str, ModelPricing] | None = None) -> ModelGateway` — `"openrouter"` → `OpenRouterModelGateway(api_key, pricing=pricing)`; anything else → `UnknownProviderError`. Adding a provider later is one registry entry (CLAUDE.md §24).

- [ ] **Step 1: Write the failing test**

Create `tests/infrastructure/llm/test_factory.py`:

```python
import pytest

from ai.models.errors import UnknownProviderError
from infrastructure.llm import create_gateway
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway


def test_factory_builds_openrouter_gateway() -> None:
    gateway = create_gateway("openrouter", api_key="k")
    assert isinstance(gateway, OpenRouterModelGateway)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError, match="ollama"):
        create_gateway("ollama", api_key="k")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_factory.py -q`
Expected: FAIL with `ImportError: cannot import name 'create_gateway'`

- [ ] **Step 3: Write the implementation**

Replace the contents of `src/infrastructure/llm/__init__.py`:

```python
"""Provider-side model gateway implementations and the provider factory (CLAUDE.md §24)."""

from collections.abc import Mapping

from ai.models.errors import UnknownProviderError
from ai.models.gateway import ModelGateway
from ai.models.profiles import ModelPricing
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_PROVIDERS = {"openrouter": OpenRouterModelGateway}


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_factory.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Verify lint and types, full suite still green**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/llm/__init__.py tests/infrastructure/llm/test_factory.py
git commit -m "feat(infrastructure): add model gateway provider factory

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: Opt-in live smoke test and documentation

**Files:**
- Create: `tests/integration/test_openrouter_live.py`
- Modify: `README.md` (add a "Model gateway" section after the "Persistence (PostgreSQL, optional)" section)
- Modify: `docs/superpowers/plans/README.md` (roadmap row 3 → Complete)

**Interfaces:**
- Consumes: `create_gateway` (Task 8); `ModelRequest`, `Message` from `ai.models.types`.
- Produces: opt-in live integration test (skipped without `OPENROUTER_API_KEY`, CLAUDE.md §46); README section; roadmap status flip.

- [ ] **Step 1: Write the live smoke test**

Create `tests/integration/test_openrouter_live.py`:

```python
import asyncio
import os

import pytest

from ai.models.types import Message, ModelRequest
from infrastructure.llm import create_gateway

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set; live provider test skipped (CLAUDE.md §46)",
)


def test_openrouter_live_generate() -> None:
    gateway = create_gateway("openrouter", api_key=os.environ["OPENROUTER_API_KEY"])
    request = ModelRequest(
        messages=(Message(role="user", content="Reply with exactly: ok"),),
        model="z-ai/glm-5.3-flash",
        temperature=0.0,
        max_tokens=10,
        timeout_seconds=30.0,
    )
    response = asyncio.run(gateway.generate(request))
    assert response.text
    assert response.invocation.provider == "openrouter"
    assert response.invocation.status == "ok"
    assert response.usage.total_tokens > 0
```

- [ ] **Step 2: Verify the test is skipped without the key and the full suite is green**

Run: `.venv/bin/python -m pytest tests/integration/test_openrouter_live.py -q && .venv/bin/python -m pytest -q`
Expected: `1 skipped`; full suite passes

- [ ] **Step 3: Update the README**

In `README.md`, after the "Persistence (PostgreSQL, optional)" section, add:

```markdown
## Model gateway (offline by default)

LLM access goes through a provider-agnostic `ModelGateway` (`src/ai/models/`).
Tests and offline runs use the deterministic `FakeModelGateway`; live calls use
the OpenRouter adapter behind `OPENROUTER_API_KEY`:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

Model profiles (`gm`, `player`, `cheap`, `reasoning`, `creative`, `embedding`)
are configured in `config/llm.toml`. Nothing in the game calls the gateway yet —
the first consumer is the character agent (Plan 4).
```

- [ ] **Step 4: Flip the roadmap row**

In `docs/superpowers/plans/README.md`, change row 3 to:

```markdown
| 3 | `2026-09-04-model-gateway.md` | Phases 9–10 — `ModelGateway` abstraction + `FakeModelGateway`, model profiles, OpenRouter adapter | Complete |
```

- [ ] **Step 5: Final verification — lint, types, full suite, live test with key if available**

Run: `.venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q`
Expected: clean; full suite passes (live test skipped unless `OPENROUTER_API_KEY` is set — with the key set, verify it passes once; do not add the key anywhere in the repo)

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_openrouter_live.py README.md docs/superpowers/plans/README.md
git commit -m "test(integration): add opt-in live OpenRouter smoke test and document the model gateway

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Completion checklist (CLAUDE.md §73)

- What changed: new `src/ai/models/` package (types, errors, Protocol, schema validator, profiles, fake), new `src/infrastructure/llm/` package (OpenRouter adapter, factory), `config/llm.toml`, `httpx` dependency, matching tests, README + roadmap updates. No `domain/`, `application/`, or `interfaces/` changes.
- Layer ownership: AI platform owns the port and types; infrastructure owns the adapter and factory.
- Tests: deterministic, network-free (fake + `MockTransport`); live provider call is opt-in via `OPENROUTER_API_KEY`.
- Invalid LLM output corrupting state: impossible — the gateway returns validated data only and nothing connects it to game state in this plan.
- Provider leakage: `openrouter` appears only under `src/infrastructure/llm/` and as config values in `config/llm.toml`.
- Existing suite: full `pytest -q` green after every task.
