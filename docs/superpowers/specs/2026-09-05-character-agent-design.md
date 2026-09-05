# Character Agent Design (Plan 4)

**Status:** Approved design → spec
**Date:** 2026-09-05
**Phases:** 11–12 (first character agent; bounded retry and deterministic fallback)
**References:** `CLAUDE.md` (§17–20, §23, §25–28, §33, §34, §45–46, §65), `docs/superpowers/specs/2026-09-04-model-gateway-design.md` (binding for gateway contract and Plan 4 duties)

---

## 1. Purpose

The model gateway (Plan 3) has its first consumer: an AI-controlled character agent that
plays one fighter in the MVP-0 combat sandbox. The deliverable is the **decision pipeline** —
observe → build context → LLM → structured output → `AttackProposal` → deterministic
validation → execution — with bounded retry and a deterministic fallback, not action breadth.

The invariant is unchanged: **the LLM proposes, the domain decides, the engine executes,
events record.** The agent is just another caller of `GameService.submit_action`. Nothing in
this plan touches `src/domain/`.

## 2. Decisions

1. **Attack-only proposals.** The combat engine validates and resolves attacks only today.
   The agent's structured output is therefore an attack decision. Extending the action space
   (dodge, disengage, …) is deferred until the engine supports resolving them.
2. **The AI character joins the party.** With the agent flag on, the CLI adds a second,
   agent-controlled party member (Brix, fighter) alongside Arin. The human keeps commanding
   Arin; the agent acts on its own initiative turn. This exercises configurable party size
   (CLAUDE.md §17) with a minimal CLI change.
3. **Split architecture (Approach 1).**
   - `src/ai/agents/` — game-free decision runtime: message assembly, gateway bridging,
     schema enforcement, transport-retry policy, agent-layer error taxonomy. Zero D&D
     knowledge, zero game imports.
   - `src/application/agents/` — the game-aware agent: perception from `GameView`, prompt
     building, JSON→proposal mapping, decision-attempt loop with rejection feedback,
     deterministic fallback, turn reporting.
   - Composition root (CLI `build_service` pattern) wires profiles → gateway → runtime →
     agent → service.
4. **Two bounded budgets with distinct jobs** (refinement of the presented "one shared
   budget" — model-error transport retries and illegal-proposal retries have different
   shapes; conflating them makes one knob lie about the other):
   - **Transport retries** (`RetryPolicy`, inside `AgentRuntime`): transient model failures
     — `ModelTimeoutError`, `ModelUnavailableError`, `ModelRateLimitedError`,
     `ModelInvalidResponseError` (the empty-content case; GLM reasoning tokens can consume
     `max_tokens`). Same request re-sent, small backoff, injectable sleep for tests.
     Default `max_attempts: int = 3`.
   - **Action attempts** (inside `AgentTurnService`): `max_action_retries = 2`
     (CLAUDE.md §28's example) → up to 3 LLM decision attempts per turn. An engine
     rejection (`TurnReport.accepted == false`) feeds the rejection reason back into the
     next prompt and consumes one attempt. Exhaustion → deterministic fallback.
   - **Either budget exhausting triggers the fallback.** Non-retryable model errors
     (`MissingAPIKeyError`, `UnsupportedSchemaError`, `ModelRequestError`, config/profile
     errors) do **not** fall back — they raise loudly as `AgentRuntimeMisconfiguredError`
     (a config or programming bug must not be silently masked by a fallback policy).
5. **Retry classification is keyed off exception types**, never off `error_kind` strings.
   `error_kind` stays telemetry-only (it lives on `LLMInvocation`). The retryable set is an
   explicit tuple of exception classes in `src/ai/agents/retry.py`.
6. **Information asymmetry is respected (CLAUDE.md §20).** The agent's perception is built
   from `GameView` by explicit field selection: its own character in full (HP, AC, conditions,
   weapon), round/turn/initiative order, and opponents as **name + defeated status only**.
   `CharacterView.hp_current` of enemies is deliberately dropped — the agent never sees
   exact enemy HP. Enemy AC and hidden world state are likewise excluded.
7. **Observable rationale, not chain-of-thought (§33).** The model returns a short explicit
   `public_message`, which the CLI prints as the character's line. Hidden reasoning is never
   requested, displayed, or persisted.
8. **Fallback is invisible to the rules.** The fallback produces a plain `AttackProposal`
   (first living opponent from `GameView.enemies` — deterministic, implemented in the
   application layer rather than reusing the domain's `SimpleMeleeEnemyPolicy`, which
   requires a raw `Game` the agent service does not hold) through the same `submit_action`
   path — identical validation, identical events. The only trace is
   `proposal_source="fallback"` on the report, so evaluation later cannot mistake fallback
   behavior for model behavior (§65).
9. **The runtime is synchronous.** The gateway is async until Plan 10 (FastAPI); callers
   bridge with `asyncio.run()` (Plan 3 spec, decision 1). `AgentRuntime` exposes a
   synchronous API so the application layer never touches asyncio.
10. **Offline by default.** CI and tests never require a real LLM (§46): the fake gateway
    path drives the full agent loop. The only live call in the repo remains the opt-in
    Plan 3 smoke test. A `--agent fake` CLI mode demos the whole feature offline.

## 3. Components

### 3.1 `src/ai/agents/` — decision runtime (game-free)

```
src/ai/agents/
├── __init__.py     # package docstring: game-free agent runtime over the model gateway
├── errors.py       # AgentRuntimeError, AgentRuntimeMisconfiguredError
├── retry.py        # RetryPolicy, RETRYABLE_MODEL_ERRORS, is_retryable(exc)
└── runtime.py      # AgentRuntime
```

**`errors.py`**

```python
class AgentRuntimeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_invocation: LLMInvocation | None = None,
    ) -> None: ...

class AgentRuntimeMisconfiguredError(AgentRuntimeError):
    """Non-retryable model/config failure; retrying an identical request cannot help."""
```

Both carry the attempt count and the last `LLMInvocation` (telemetry rides on the error —
same convention as `ModelError.invocation`). The AI layer defines its own errors; it does
not import the domain's `AgentDecisionFailedError`.

**`retry.py`**

```python
RETRYABLE_MODEL_ERRORS: tuple[type[ModelError], ...] = (
    ModelTimeoutError,
    ModelUnavailableError,
    ModelRateLimitedError,
    ModelInvalidResponseError,
)

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3          # >= 1
    backoff_seconds: float = 0.0
    sleep: Callable[[float], None] = time.sleep

def is_retryable(exc: BaseException) -> bool
```

`is_retryable` returns `True` exactly for the tuple in `RETRYABLE_MODEL_ERRORS` (plain
`isinstance` check — the gateway raises typed errors directly rather than wrapping).
`RetryPolicy` validates `max_attempts >= 1` at construction.

**`runtime.py`**

```python
class AgentRuntime:
    def __init__(self, gateway: ModelGateway, retry_policy: RetryPolicy = RetryPolicy()) -> None: ...

    def decide_structured(
        self,
        *,
        profile: ModelProfile,
        system: str,
        user: str,
        schema: Mapping[str, Any],
    ) -> StructuredModelResponse: ...
```

One decision = one bounded loop: build `Message(system)/Message(user)`, `profile.to_request(...)`,
then up to `max_attempts` calls to `gateway.generate_structured(request, schema)` via
`asyncio.run(...)`. Retryable `ModelError` → sleep `backoff_seconds` and retry. Non-retryable
`ModelError` → raise `AgentRuntimeMisconfiguredError` (chained, with `.invocation`). Budget
exhausted → `AgentRuntimeError` (with attempt count + last invocation). The schema passed in
must use only the gateway's supported JSON-Schema subset (`type`, `properties`, `required`,
`enum`, `additionalProperties`; the subset pinned by Plan 3's validator tests) — passing a
schema outside the subset raises `UnsupportedSchemaError` from the validator, which is
non-retryable by design.

### 3.2 `src/application/agents/` — game-aware character agent

```
src/application/agents/
├── __init__.py
├── profiles.py          # AgentProfile, AgentProfileCatalog, load_agent_profiles(path)
├── perception.py        # build_perception(view, actor_id) -> AgentPerception
├── character_agent.py   # CharacterAgent, ATTACK_DECISION_SCHEMA, AgentDecision
├── agent_turn_service.py# AgentTurnService, AgentTurnReport
└── fake_script.py       # scripted decisions for --agent fake (offline demo/tests)
```

**`profiles.py`** — mirrors the model-profile loader's structure-validation-only pattern
(stdlib `tomllib`; bad shapes raise `AgentProfileError(ValueError)`):

```python
@dataclass(frozen=True)
class AgentProfile:
    name: str
    character_name: str
    character_class: str          # validated against CharacterClass values
    persona: str
    objective: str
    model_profile: str            # key into ModelProfileCatalog

@dataclass(frozen=True)
class AgentProfileCatalog:
    max_action_retries: int       # from [agent] table, default 2, >= 0
    agents: Mapping[str, AgentProfile]
    def get(self, name: str) -> AgentProfile  # AgentProfileNotFoundError on miss

def load_agent_profiles(path: str | Path) -> AgentProfileCatalog
```

Config file `config/agents.toml`:

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

**`perception.py`** — the §20 boundary. Built from `GameView` by field selection:

```python
@dataclass(frozen=True)
class OpponentBrief:
    id: str
    name: str
    is_defeated: bool

@dataclass(frozen=True)
class AgentPerception:
    round_number: int
    active_actor_id: str
    self_view: CharacterView            # full own state
    opponents: tuple[OpponentBrief, ...]  # name + defeated status ONLY (no HP/AC)
    initiative_order: tuple[str, ...]   # names, in turn order

def build_perception(view: GameView, actor_id: str) -> AgentPerception
```

Raises `AgentNotInCombatError` (application-layer error) if `view.combat` is `None` or the
actor is not the active combatant. Enemies' `hp_current`/`armor_class` are structurally
absent from `AgentPerception` — a test pins this.

**`character_agent.py`** — one agent's identity and decision mapping:

```python
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

@dataclass(frozen=True)
class AgentDecision:
    proposal: AttackProposal
    public_message: str
    invocation: LLMInvocation

class CharacterAgent:
    def __init__(self, profile: AgentProfile) -> None: ...
    def build_system_prompt(self) -> str
    def build_user_prompt(self, perception: AgentPerception, *, rejection: str | None = None) -> str
    def map_decision(self, data: Mapping[str, Any], perception: AgentPerception) -> AgentDecision
```

The system prompt carries persona + objective + engagement rules (attack only; choose a
target id from the listed opponents; answer only in the JSON schema). The user prompt
carries the perception — serialized text, no enemy HP anywhere. When `rejection` is
non-`None`, the prompt appends the engine's rejection reason and asks the model to choose
again. `map_decision` validates `action_type == "attack"`, resolves `target_id` to a known
living opponent from the perception (unknown/dead target → treated as a rejected
attempt, not an exception), and requires a non-empty `public_message`.

**`agent_turn_service.py`** — the use case; the only component that touches the gateway loop:

```python
@dataclass(frozen=True)
class AgentTurnReport:
    actor_id: str
    accepted: bool
    proposal_source: str            # "model" | "fallback"
    action_attempts: int            # LLM decision attempts used this turn
    rejection_reasons: tuple[str, ...]
    fallback_reason: str | None     # why the fallback fired (None if model succeeded)
    public_message: str | None
    invocations: tuple[LLMInvocation, ...]
    turn_report: TurnReport         # the underlying deterministic result

class AgentTurnService:
    def __init__(
        self,
        game_service: GameService,
        runtime: AgentRuntime,
        catalog: ModelProfileCatalog,
        agent_profiles: AgentProfileCatalog,
        *,
        max_action_retries: int | None = None,   # default from agent_profiles
    ) -> None: ...

    def register(self, actor_id: CharacterId, profile: AgentProfile) -> None
    def is_agent_controlled(self, actor_id: CharacterId) -> bool
    def take_turn(self, game_id: GameId, actor_id: CharacterId) -> AgentTurnReport
```

`take_turn` flow: `get_view` → `build_perception` → attempt loop
(`max_action_retries + 1` decision attempts): `runtime.decide_structured(...)` →
`map_decision` → `game_service.submit_action(SubmitActionCommand(...))` → accepted →
report; rejected → record `TurnReport.reason`, rebuild prompt with feedback, next attempt.
Transport-level retries happen inside the runtime (decision 4). All attempts exhausted →
fallback: first living opponent from the current `GameView.enemies` → `AttackProposal` →
`submit_action`, `proposal_source="fallback"`. Non-retryable runtime errors propagate.
Every `StructuredModelResponse.invocation` and every error's `.invocation` accumulates in
the report.

**`fake_script.py`** — offline demo/test support: a helper that wraps `FakeModelGateway`
and enqueues a repeating canned decision ("attack the first living opponent" + a fixed
`public_message`) before each `decide_structured` call, so the queue never exhausts.

### 3.3 Composition root & CLI

`src/interfaces/cli/app.py` gains:

```
--agent {off,llm,fake}    # default: off
```

- `off` (default): the game behaves exactly as today — byte-identical human loop.
- `llm`: requires `OPENROUTER_API_KEY` (fail-fast `ValueError`, same as `DATABASE_URL`);
  loads `config/llm.toml` + `config/agents.toml`; `create_gateway("openrouter", api_key=...)`;
  builds `AgentRuntime`; adds Brix (same fighter statline builder as Arin) via
  `add_character`; registers the agent; prints one line announcing the agent joined.
- `fake`: identical wiring, `FakeModelGateway` + `fake_script` instead of the provider.

CLI loop change is one branch: active actor agent-controlled →
`agent_turn_service.take_turn(...)`, then render: `Brix: "<public_message>"` plus a concise
telemetry line (attempts, source; tokens/cost when available) — no logging framework, no
sinks (Plan 8). Otherwise the existing human prompt path, untouched.

## 4. Failure-mode table

| Failure | Where | Behavior |
|---|---|---|
| `ModelTimeoutError` / `ModelUnavailableError` / `ModelRateLimitedError` / `ModelInvalidResponseError` | runtime | transport retry (≤ `RetryPolicy.max_attempts`), backoff between tries |
| `MissingAPIKeyError`, `UnsupportedSchemaError`, `ModelRequestError`, profile/config errors | runtime | `AgentRuntimeMisconfiguredError`, propagates — no fallback |
| Transport budget exhausted | runtime | `AgentRuntimeError` → service treats as a consumed decision attempt |
| Model proposes unknown/dead target, or bad JSON shape that passes schema | service | counts as a rejected attempt (reason fed back), next attempt |
| Engine rejects the proposal | service | `ActionRejected` already emitted by engine, nothing mutated; reason fed back, next attempt |
| Decision budget exhausted | service | deterministic fallback attack via `submit_action`, `proposal_source="fallback"` |
| Agent's turn while combat inactive / actor mismatch | perception | `AgentNotInCombatError` |

## 5. Testing

No real LLM in CI (§46). `asyncio.run` bridging only — no pytest-asyncio, matching repo
conventions. New tests:

- `tests/ai/agents/test_retry.py` — retryable tuple classification; policy validation.
- `tests/ai/agents/test_runtime.py` — success on attempt 2 after
  `enqueue_error(ModelTimeoutError())` (the Plan 3 fake's intended retry-test path);
  exhaustion → `AgentRuntimeError` with attempts; non-retryable →
  `AgentRuntimeMisconfiguredError` on attempt 1; schema enforcement exercised through the
  real validator; invocations recorded; injectable sleep never really sleeps.
- `tests/application/agents/test_profiles.py` — TOML loading, defaults, malformed structures.
- `tests/application/agents/test_perception.py` — field selection; **enemy HP/AC absent**;
  not-your-turn raises.
- `tests/application/agents/test_character_agent.py` — prompt contains persona/objective/
  perception and no enemy HP; decision mapping; bad target treated as rejection;
  rejection-feedback prompt includes the reason.
- `tests/application/agents/test_agent_turn_service.py` — scripted fake gateway:
  model-succeeds path; rejection-then-retry path; exhaustion → fallback proposal is legal
  and accepted; invocation accumulation; full deterministic combat completes with the agent
  in the party.
- `tests/interfaces/test_cli_agent.py` — `--agent fake` plays a full fight offline;
  `--agent llm` without `OPENROUTER_API_KEY` fails fast; `--agent off` output unchanged.

## 6. Non-goals

- Memory, vector retrieval, context engineering beyond the inline prompt (Plan 7).
- Telemetry sinks, logging framework, OpenTelemetry (Plan 8).
- GM agent, NPC conversation, party communication (Plans 5+).
- Action-space expansion (dodge/disengage/movement) — waits on engine support.
- Tool calling, streaming, embeddings, prompt-template library.
- FastAPI / async application layer (Plan 10+; `asyncio.run` bridge stays).
- Any change to `src/domain/`, dice, combat math, or event types.

## 7. Global constraints

- Domain layer untouched; stdlib-only; no new runtime dependencies (gateway + httpx already
  present from Plan 3).
- Provider names (`openrouter`, model ids) appear only under `src/infrastructure/llm/` and
  as config values in `config/*.toml`.
- All model profiles remain `z-ai/glm-5.3-flash` (standing user directive until final version).
- Secrets from environment only; never committed or logged. No API key material anywhere in
  the repo or test output.
- No private chain-of-thought requested, displayed, or persisted (§33).
- mypy strict, ruff clean, pytest green offline at every task boundary; conventional commits
  scoped by layer with the Co-Authored-By trailer.

## 8. Completion checklist

- [ ] `src/ai/agents/` contains zero D&D/domain imports (enforced by a test).
- [ ] `src/domain/` has zero diff vs `master`.
- [ ] Agent turn cannot mutate state except through `submit_action`.
- [ ] Enemy HP/AC never enter any prompt (pinned by test).
- [ ] Retries bounded and configurable; fallback deterministic; no infinite loops.
- [ ] Full suite green offline without `OPENROUTER_API_KEY` or `DATABASE_URL`.
- [ ] `--agent off` behavior identical to current CLI.
- [ ] Provider abstraction intact; no provider SDK outside infrastructure.
