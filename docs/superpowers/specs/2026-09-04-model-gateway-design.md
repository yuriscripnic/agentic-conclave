# Model Gateway Design (Plan 3)

- **Date:** 2026-09-04
- **Status:** Approved design (brainstorming complete; implementation plan follows)
- **Covers:** Implementation Plan doc Phases 9–10 (`ModelGateway`, `ModelRequest`, `ModelResponse`, `StructuredModelResponse`, `LLMInvocation`, `FakeModelGateway`), plus model profiles and the OpenRouter adapter
- **Roadmap row:** 3 — *model-gateway* in `docs/superpowers/plans/README.md`

## Goal

Introduce the AI platform's model boundary: a provider-agnostic, async `ModelGateway`
port with value types, a deterministic offline `FakeModelGateway`, a thin OpenRouter
adapter (httpx, no provider SDK), and TOML-configured model profiles
(`gm / player / cheap / reasoning / creative / embedding`). Plan 4's character agent
becomes the first consumer; nothing in this plan wires a gateway into the game.

**Invariant preserved:** the gateway transports requests and records telemetry. It
never decides game rules, never mutates game state, and never sees domain concepts
(characters, dice, HP). "LLMs propose" starts one layer up (Plan 4).

## Decision log (recorded during brainstorming, 2026-09-04)

1. **Async interface.** `async def generate(...)` per CLAUDE.md §23, even though the
   existing codebase is synchronous. First async code in the project; callers bridge
   with `asyncio.run()` until Plan 10 (FastAPI) arrives.
2. **httpx, not the OpenAI SDK.** OpenRouter is an OpenAI-compatible REST API; one
   small dependency (CLAUDE.md §55), adapter stays ~100 lines for the shipped
   capabilities. CLAUDE.md §24 permits SDKs under `infrastructure/llm/`, but YAGNI.
3. **Capabilities: `generate` + `generate_structured` only.** `stream()` and
   `embed()` are deferred until a real consumer exists (GM narration / Plan 7
   memory), per Phase 9's "not every provider needs every capability initially".
   Adding methods to the Protocol later is cheap inside the monolith.
4. **Approach A — AI-owned port.** Protocol and value types live in `src/ai/models/`
   (CLAUDE.md §7 lists `ModelGateway` as an AI-platform abstraction, reusable beyond
   D&D). Infrastructure implements the port; `ai/` never imports infrastructure —
   same direction as Plan 2's `application/ports.py` + persistence adapters.
5. **Schema enforcement is local and shared.** The adapter requests
   `response_format: {"type": "json_object"}` and validates against the JSON-Schema
   subset with a stdlib validator shared with the fake — identical validation offline
   and online, zero new dependencies.
6. **`LLMInvocation` type ships now; sinks ship in Plan 8.** Every call produces its
   telemetry record (carried on the response, or on the exception when the call
   fails). Structured logging, correlation-ID propagation, and persistence of
   invocations are roadmap row 8.
7. **Retry policy is not in the gateway.** Bounded retries and deterministic
   fallback belong to Plan 4's decision pipeline (CLAUDE.md §28). The gateway is
   single-attempt transport.
8. **Model IDs verified** against OpenRouter's catalog on 2026-09-04: Z.ai GLM
   namespace (`z-ai/glm-5.3-flash`, `z-ai/glm-5.2`). IDs are config values, not code.

## Architecture & module layout

```text
src/ai/models/                      ← AI platform's model boundary (no game concepts, no providers)
├── __init__.py
├── types.py        Message · ModelRequest · Usage · ModelResponse ·
│                   StructuredModelResponse · LLMInvocation
├── errors.py       ModelError taxonomy (AI-layer errors, not DomainErrors)
├── gateway.py      ModelGateway Protocol — async generate / generate_structured
├── schema.py       minimal stdlib JSON-Schema-subset validator (shared by fake + adapter)
├── profiles.py     ModelProfile · ModelProfileCatalog · load_model_profiles(path)
└── fake.py         FakeModelGateway — deterministic, scriptable, offline

src/infrastructure/llm/
├── __init__.py     create_gateway(provider, ...) factory (provider-name → adapter registry)
└── openrouter/
    ├── __init__.py
    └── adapter.py  OpenRouterModelGateway — httpx, env-var key, error mapping

config/
└── llm.toml        model profiles + optional per-model pricing (no secrets)

tests/ai/models/    gateway-layer tests (schema, fake, profiles, types)
tests/infrastructure/llm/   adapter tests via httpx.MockTransport (offline)
tests/integration/  opt-in live OpenRouter smoke test (skipped without API key)
```

**Dependency direction:**

```text
infrastructure/llm/openrouter ──implements──▶ ai/models/gateway.ModelGateway (Protocol)
application & future ai/agents ──consume──▶ ModelGateway Protocol only
```

- `src/ai/` stays provider-free and game-free: it knows messages, schemas, profiles,
  tokens, costs — never OpenRouter endpoints, never characters or dice.
- `src/infrastructure/llm/openrouter/` is the only module that knows OpenRouter
  headers, endpoints, or reads the API key.
- Nothing in `domain/` or `application/` changes in this plan.

## Core types (exact contracts)

```python
# src/ai/models/types.py
from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]

@dataclass(frozen=True)
class Message:
    role: Role
    content: str

@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[Message, ...]        # ordered conversation so far
    model: str                           # resolved concrete model id, e.g. "z-ai/glm-5.2"
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
    provider: str                        # "openrouter" | "fake"
    model: str
    operation: str                       # "generate" | "generate_structured"
    status: str                          # "ok" | "error" | "timeout"
    error_kind: str | None               # "rate_limited" | "invalid_response" | ... (closed-ish;
                                         #   metadata only — never payloads, prompts, or reasoning)
    latency_ms: int
    input_tokens: int | None             # None when the call failed before usage was known
    output_tokens: int | None
    estimated_cost_usd: float | None
    request_id: str                      # uuid4().hex, generated by the gateway at call start

@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str                           # model id that actually served the call
    usage: Usage
    finish_reason: str                   # provider-neutral subset; unknown values pass through
    invocation: LLMInvocation

@dataclass(frozen=True)
class StructuredModelResponse:
    data: dict[str, Any]                 # schema-validated JSON
    model: str
    usage: Usage
    finish_reason: str
    invocation: LLMInvocation
```

Design points:

- **`ModelRequest.model` is the resolved concrete id.** Profile resolution
  (`"cheap"` → `"z-ai/glm-5.3-flash"`) happens at config load / composition time,
  never inside a gateway. `ModelProfile` gains a helper
  `to_request(messages: Sequence[Message]) -> ModelRequest` so callers never
  hand-assemble provider strings.
- **Schema is per-call** (`generate_structured(request, schema)`) — one agent may
  use different schemas for different decision types (§25 action proposal vs §33
  short rationale).
- **`finish_reason`** maps OpenRouter's raw values into the neutral subset
  (`stop`, `length`, `content_filter`, `error`); unknown values pass through
  verbatim rather than being guessed.
- **`LLMInvocation` metadata only** (§34): no prompts, no response text, no hidden
  chain-of-thought, no API keys. `error_kind` is a short classifier string.
- **Failed calls carry telemetry on the exception:** `ModelError.invocation` is
  `LLMInvocation | None`, populated by implementations before raising, so Plan 8
  sinks can collect failed-call records without changing signatures.

## Protocol

```python
# src/ai/models/gateway.py
from typing import Any, Mapping, Protocol

class ModelGateway(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    async def generate_structured(
        self, request: ModelRequest, schema: Mapping[str, Any]
    ) -> StructuredModelResponse: ...
```

Both methods are single-attempt (Decision 7). Implementations MUST populate
`invocation` on every success and every raised `ModelError`.

## JSON-Schema subset validator

`src/ai/models/schema.py` exposes one function:

```python
def validate_against_schema(data: Any, schema: Mapping[str, Any]) -> None
    # raises ModelInvalidResponseError with a path-precise message, e.g.
    # "data.parameters.target_id: expected string, got int"
    # raises UnsupportedSchemaError for keywords outside the subset
```

Supported keywords — exactly what Plan 4's action-proposal schemas need:

```text
type: object | string | number | integer | boolean | array
properties · required · additionalProperties: false
enum (any JSON type) · items (for arrays) · minimum / maximum (numbers)
```

Anything outside the subset (`oneOf`, `patternProperties`, …) raises
`UnsupportedSchemaError` at call time — loud, not silent. When a future plan needs
richer schemas, the validator grows then (YAGNI).

## Structured-output flow

Identical three steps in the adapter and the fake:

```text
generate_structured(request, schema)
  ↓ provider call with response_format: {"type": "json_object"}
  ↓ parse JSON            → failure: ModelInvalidResponseError
  ↓ validate vs schema    → failure: ModelInvalidResponseError (path-precise)
  ↓ StructuredModelResponse(data, usage, invocation)
```

A non-JSON `content` from a `json_object` request is a real error — surfaced, not
coerced. Because the fake runs the same validator, Plan 4's tests exercise the exact
validation path production uses.

## FakeModelGateway

```python
# src/ai/models/fake.py
fake = FakeModelGateway()
fake.enqueue_text("I will strike the goblin.")            # → next generate()
fake.enqueue_structured({"action_type": "attack", ...})   # → next generate_structured()
fake.enqueue_error(ModelTimeoutError())                   # → next call raises (retry tests, Plan 4)
```

- **Deterministic and scriptable** — no randomness, no network (Phase 10, §46).
  Responses come out in enqueue order from one shared per-instance queue.
- **Enqueued structured payloads are validated against the schema at call time** —
  a test scripting an invalid action proposal fails loudly in the test, mirroring
  §25/§28 (a syntactically valid LLM answer is not automatically a valid action).
- **Exhausted queue raises `FakeGatewayExhaustedError`** — a test making more calls
  than it scripted has a bug; the fake surfaces it instead of improvising.
- **Records every `LLMInvocation`** (status ok/error) in `fake.invocations` for
  assertions, and stamps `provider="fake"`.
- Structured responses default to synthetic-but-plausible usage counts
  (deterministic constants), `finish_reason="stop"`.

## OpenRouter adapter

`src/infrastructure/llm/openrouter/adapter.py` — the only OpenRouter-aware module:

- **Constructor:**
  `OpenRouterModelGateway(api_key: str, *, base_url: str = "https://openrouter.ai/api/v1",
  client: httpx.AsyncClient | None = None, pricing: Mapping[str, ModelPricing] | None = None,
  app_url: str | None = None, app_title: str | None = None)`
  - Empty/missing key → `MissingAPIKeyError` at construction (fail-fast).
  - Injected `client` lets tests mount `httpx.MockTransport` — the adapter is
    tested fully offline.
  - `pricing` keys are model ids.
- **Request mapping:** OpenAI-compatible `POST /chat/completions`; `messages`
  array, `temperature`, `max_tokens` passthrough; headers `Authorization: Bearer`,
  plus `HTTP-Referer`/`X-Title` from `app_url`/`app_title` when provided.
  `generate_structured` adds `response_format: {"type": "json_object"}`.
- **Timeouts:** `request.timeout_seconds` → per-call `httpx.Timeout`; callers
  control urgency, adapter carries no hidden global timeout.
- **Error mapping** — no raw `httpx` exception ever escapes:

| Condition | Raised error |
|---|---|
| `httpx.TimeoutException` | `ModelTimeoutError` |
| HTTP 429 | `ModelRateLimitedError` (`.retry_after_seconds: float \| None` from `Retry-After`) |
| other HTTP 4xx | `ModelRequestError` (bad key, unknown model, malformed request) |
| HTTP 5xx | `ModelUnavailableError` |
| anything else | `ModelError` (base catch-all) |

- **Response mapping:** `choices[0].message.content` → text; `usage` → `Usage`;
  `model` echo; finish reason mapped per the neutral subset. Empty `choices` or
  missing content → `ModelInvalidResponseError`.
- **Cost:** `pricing[model]` × usage → `estimated_cost_usd`; absent pricing →
  `None`. No hardcoded price table in code.
- **`invocation` on errors:** every mapped exception carries its `LLMInvocation`
  (`status="error"`, appropriate `error_kind`, measured latency) before raising.

## Error taxonomy

`src/ai/models/errors.py` — AI-layer errors; the domain never imports them:

```python
ModelError                          # base; .invocation: LLMInvocation | None
├── ModelTimeoutError
├── ModelRateLimitedError           # .retry_after_seconds: float | None
├── ModelRequestError               # our request was wrong (config/key/model id)
├── ModelUnavailableError           # provider-side failure / 5xx
├── ModelInvalidResponseError       # unparsable or schema-invalid output
├── MissingAPIKeyError
└── UnsupportedSchemaError          # schema uses keywords outside the subset

FakeGatewayExhaustedError           # fake-only; defined in fake.py
```

Configuration/loader errors (same module; raised at startup, before any call):

```python
ProfileConfigError                  # llm.toml missing or unreadable
ProfileNotFoundError                # catalog.get("nonexistent")
InvalidProfileError                 # structurally invalid entry (missing provider/model)
UnknownProviderError                # factory: provider name has no adapter registered
```

Extends CLAUDE.md §49's `ModelError`/`ModelTimeout` into a catchable hierarchy.

## Configuration

`config/llm.toml` (checked in; contains **no secrets** — the key comes from
`OPENROUTER_API_KEY`, already present in `.env.example`):

```toml
default_provider = "openrouter"

[profiles.gm]                # narration quality
provider = "openrouter"
model = "z-ai/glm-5.2"
temperature = 0.8
max_tokens = 1024

[profiles.player]            # default character-agent brain (volume consumer)
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.7
max_tokens = 1024

[profiles.cheap]             # high-volume, low-stakes calls
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.5
max_tokens = 512

[profiles.reasoning]
provider = "openrouter"
model = "z-ai/glm-5.2"
temperature = 0.3

[profiles.creative]
provider = "openrouter"
model = "z-ai/glm-5.2"
temperature = 1.0

[profiles.embedding]         # reserved — unused until Plan 7 (pgvector memory)
provider = "openrouter"
model = "z-ai/glm-5.3-flash"

[pricing."z-ai/glm-5.3-flash"]   # verified 2026-09-04; USD per million tokens
input_per_million_usd = 0.07125
output_per_million_usd = 0.2375

[pricing."z-ai/glm-5.2"]
input_per_million_usd = 0.4875
output_per_million_usd = 1.56
```

- **Loader:** `load_model_profiles(path) -> ModelProfileCatalog` (stdlib `tomllib` —
  no pyyaml). `ModelProfileCatalog.get(name) -> ModelProfile` raises
  `ProfileNotFoundError`; structurally invalid entries (missing `provider`/`model`)
  raise `InvalidProfileError`; missing file raises `ProfileConfigError`. The loader
  validates structure only.
- **`ModelProfile`** frozen dataclass: `name, provider, model, temperature: float = 0.7,
  max_tokens: int | None = None`, plus `to_request(messages)` (Section "Core types").
- **Factory:** `src/infrastructure/llm/__init__.py` exposes
  `create_gateway(provider: str, *, api_key: str, pricing: Mapping[str, ModelPricing] | None = None) -> ModelGateway`.
  `"openrouter"` → `OpenRouterModelGateway`; anything else → `UnknownProviderError`
  at startup. Adding Ollama/OpenAI/Anthropic later is one registry entry
  (CLAUDE.md §24).
- Profile → gateway wiring (who reads the TOML, who calls the factory) is a
  composition-root concern that lands with Plan 4's first consumer.

## Testing strategy

TDD throughout; the full suite runs network-free.

| File | Covers |
|---|---|
| `tests/ai/models/test_schema.py` | validator: each supported keyword, nested paths, path-precise error messages, `additionalProperties: false`, enum/minimum/maximum, `UnsupportedSchemaError` on out-of-subset keywords |
| `tests/ai/models/test_fake.py` | enqueue order for text/structured, queue exhaustion, schema validation of enqueued payloads, error injection, `invocations` recording, `provider="fake"` |
| `tests/ai/models/test_profiles.py` | TOML load, defaults, `ProfileNotFoundError`, `InvalidProfileError`, `ProfileConfigError`, pricing parse, `to_request` |
| `tests/ai/models/test_types.py` | `Usage.total_tokens`, frozen-ness of value types |
| `tests/infrastructure/llm/test_openrouter_adapter.py` | `httpx.MockTransport`: success mapping (text, usage, model echo, finish reasons), all five error mappings incl. `Retry-After`, structured parse+validate, cost computation, missing/empty key at construction, per-call timeout propagation |
| `tests/integration/test_openrouter_live.py` | opt-in single `generate()` smoke call; **skipped unless `OPENROUTER_API_KEY` is set** (§46: real provider calls belong in optional integration tests) |

Also verified per CLAUDE.md §54/§73: full existing suite still passes, `ruff check`
and `mypy --strict` clean, and `src/ai/` contains no provider, Rich, psycopg, or
domain imports.

## Documentation updates

- `README.md`: short "Model gateway" section after Persistence — offline fake by
  default, live OpenRouter behind `OPENROUTER_API_KEY` + `config/llm.toml`.
- `docs/superpowers/plans/README.md`: row 3 → Complete at execution end.
- `.env.example`: no change needed (key placeholder already present).

## Explicit non-goals (Plan 3)

- `stream()` / `embed()` — added when GM narration / Plan 7 need them.
- Wiring any gateway into `GameService`, the CLI, or agents — Plan 4.
- Retry/backoff/fallback policy — Plan 4 decision pipeline (§28).
- Telemetry sinks, structured logging, correlation-ID propagation, invocation
  persistence — Plan 8 (roadmap row 8). Only the `LLMInvocation` type ships now.
- Context building, prompt templates, memory — Plan 7.
- Tool calling — Plan 4/5 with the agent runtime.
- No `domain/` or `application/` file changes; no new dev dependencies.

## Completion standard (CLAUDE.md §73)

- **What changed:** new `src/ai/models/` package, `src/infrastructure/llm/` package,
  `config/llm.toml`, matching tests; nothing else.
- **Which layer owns it:** AI platform (`ai/models/`) owns the port and types;
  infrastructure owns the adapter; interfaces/application untouched.
- **Tests:** table above; deterministic, network-free, `FakeModelGateway`-based.
- **Works without a real LLM:** yes — the fake and `MockTransport` cover everything;
  the live test is opt-in.
- **Invalid LLM output corrupting state:** impossible by construction — the gateway
  returns validated data only, and nothing in this plan connects it to game state.
- **Provider leakage:** `openrouter` appears only under `src/infrastructure/llm/`
  and in `config/llm.toml` values.
