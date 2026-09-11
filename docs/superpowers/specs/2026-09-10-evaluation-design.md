# Evaluation Design — Phase 18 (Roadmap Plan #9)

Date: 2026-09-10
Status: Approved (design sections approved in session; see git history). Amended during
planning: session package placement (§2.4, §4.1), scenario ground truth (§4.4), and the
sanctioned initiative-determinism domain fix (§6).
Upstream: `CLAUDE.md` (§28, §34, §44, §45, §46, §47, §50, §53, §63, §65, §66, §67), `docs/Agentic Conclave-Implementation Plan.md` §21 (Phase 18), `docs/superpowers/plans/README.md` row #9

## 1. Goal

Make evaluation a first-class, repeatable feature of the platform: scripted scenarios drive
real game sessions through the application layer, collect what actually happened (domain
events, enriched LLM invocations, turn reports, party traffic), and report a core set of
metrics — legal-action rate, rejections, retries, latency, tokens/game, cost/game — plus
scenario checks for instruction adherence, cross-run consistency, and cooperation.

Two truths from §65/§66 shape everything:

- Game correctness is separate from AI quality. A poor AI decision must never corrupt game
  mechanics; evaluation measures behavior, it never relaxes rules.
- Models are comparable only on the same scenarios with the same seeds.

## 2. Decisions (made in this session)

1. **Metric scope — core measurable set.** Rule adherence / legal-action rate, invalid
   actions (rejection counts with reasons), retry counts, latency percentiles, tokens/game,
   cost/game from existing telemetry + events, PLUS scenario checks for instruction
   adherence, consistency, and cooperation. Information-leakage probes, memory relevance,
   and LLM-judged decision quality are deferred to a later plan.
2. **Offline + live.** The runner drives scripted gateways by default (fully deterministic,
   CI-safe). `--provider openrouter` builds real gateways from model profiles and
   `OPENROUTER_API_KEY` (environment only, never committed) so live model comparison works
   the day the plan ships.
3. **Results: JSON files + console table.** Each run writes
   `eval-results/<scenario>-<provider>-<model>-<seed>-<UTC timestamp>.json`
   (`eval-results/` is git-ignored) and `conclave-eval` prints a Rich summary table.
   Committed baselines are out of scope.
4. **Approach A: `src/evaluation/` package over a shared session factory.** The CLI's game
   wiring is extracted into a composition root in a new top-level `src/session/` package that
   the CLI, the evaluation harness, and the future API layer (Plan 10) all share — §63's
   shared-contract rule, paid forward. (Amended during planning: the composition root must
   import infrastructure to do its job, so it cannot live in the infrastructure-free
   application layer — see §4.1.)

## 3. Current state (ground truth this design builds on)

- **Game wiring exists only inside `interfaces/cli/app.py`**: `build_service(db)` wires
  `GameService`; `_wire_party(...)` builds memory + `AgentTurnService`; `_wire_gm(...)`
  builds `GmDirector`; the input loop inlines `parse_input`, `_resolve_target`, attack
  dispatch, enemy-turn advancement, and GM reactions. Nothing else can run a session
  programmatically.
- **Enriched `LLMInvocation` (Plan 8)** already carries everything the numeric metrics need:
  `provider`, `model`, `operation`, `status`, `attempt` (>1 ⇒ retry), `latency_ms`,
  `input_tokens`, `output_tokens`, `estimated_cost_usd`, `agent_id`, `game_id`,
  `correlation_id`. Never contains prompts, payloads, or reasoning (§34).
- **Domain events emit the adherence signals**: `src/domain/combat/engine.py` emits
  `ActionRejected` (`actor_id`, `action_type`, `reason`) when an attack fails rules
  validation and `AttackRequested` when it passes — so `proposals = AttackRequested +
  ActionRejected[attack]` and the legal-action rate is well-defined without new
  instrumentation. `AttackResolved`, `DamageApplied`, `CharacterDefeated`,
  `CombatStarted/Ended`, `TurnStarted/Ended` cover outcomes.
- **Party communication** lives on the application-side `PartyMessageBoard`
  (`PartyMessage` records) — not a domain event; the runner snapshots it after a run.
- **Deterministic gateways exist**: `FakeModelGateway`, `ScriptedAgentGateway`,
  `ScriptedGmGateway` (re-enqueue canned decisions before every call) — offline evaluation
  needs no new fakes.
- **Suite**: 425 offline tests green; `live` marker deselects real-provider tests.

## 4. Architecture

```text
conclave-eval CLI (src/evaluation/cli.py)
  ↓
run_scenario() (src/evaluation/runner.py)
  ↓
build_session(SessionConfig) (src/session/factory.py)   ← shared with CLI, later API
  ↓  per step: human input → apply_input() (src/session/play.py) → AgentTurnService / GmDirector
  ↓  (one correlation_id per step, per Plan 8)
EventRepository + InMemoryTelemetrySink + turn reports + PartyMessageBoard
  ↓
EvalRunRecord → metrics.py → checks → report.py → JSON file + console table
```

Evaluation contains **no game rules** and never mutates game state except through
application services — the same path the CLI drives (§71 invariant: LLMs propose, the
domain decides).

### 4.1 Session factory and shared input path (src/session/ — new top-level package)

A composition root, extracted from the CLI with contracts preserved. It lives in a new
**top-level package `src/session/`**, not in `src/application/`: the composition root must
import infrastructure (repositories, gateways, telemetry sinks) to do its job, while the
application layer is kept infrastructure-free (CLAUDE.md §4 — infrastructure depends on
application/domain abstractions, never the reverse). `src/session/` sits alongside the
other top-level packages; `interfaces/` and `evaluation/` both import it.

`src/session/factory.py` — wiring only, no rules, no rendering:

- `SessionConfig` (frozen dataclass): `seed: int = 42`, `db: str = "memory"`
  (`"memory" | "postgres"`, `DATABASE_URL` env semantics preserved verbatim),
  `agent_mode: str | None = None` (`None` is the CLI's `"off"`; else `"fake" | "llm"`),
  `gm_mode: str = "off"` (`"off" | "fake" | "llm"`), `gateway: ModelGateway | None = None`
  (overrides the built gateway in every mode — eval/test injection), `provider: str | None
  = None` (llm-mode provider override).
- `GameSession` (frozen dataclass): `game_service`, `game_id: GameId`, `telemetry`
  (the fresh `InMemoryTelemetrySink` — the composite sink is built internally and passed
  to the services), `party_board: PartyMessageBoard`, `party_names: tuple[str, ...]`,
  `turn_service: AgentTurnService | None`, `gm_director: GmDirector | None`,
  `opening: GmResult | None`.
- `build_session(config) -> GameSession`: full wiring — persistence backend, telemetry
  composite (`[LoggingTelemetrySink, in-memory]` + Postgres sink when `db="postgres"` and
  `DATABASE_URL` is set), the Arin fighter, party agents (fake: scripted gateway; llm:
  real gateway; the party **join line is not printed here** — rendering stays in callers,
  which read `party_names`), GM director, encounter, `start_combat`.
- `open_session(config) -> GameSession`: `build_session` plus
  `gm_director.on_combat_open(game_id, correlation_id=new_correlation_id())` stored as
  `opening` — the session is ready to accept input. The CLI and the runner both use
  `open_session`.

`src/session/play.py` — the CLI loop's engine, moved verbatim where possible:

- `parse_input(raw)` — moved unchanged (`interfaces.cli.app` re-exports it; the existing
  test contract imports it from there, along with `build_service`).
- `PendingTurn` (frozen): `kind` (`"enemy" | "agent"`), `turn_report`,
  `agent_report` (`AgentTurnReport | None`), `gm_result` (`GmResult | None`).
- `InputOutcome` (frozen): `kind` (`"empty" | "command" | "unknown" | "attack" | "say" |
  "no_target" | "error"`), `argument`, `turn_report`, `gm_result`, `error`
  (`str | None` — a captured `DomainError` message).
- `advance(session) -> PendingTurn | None`: drives non-player turns — enemy active ⇒
  `run_active_enemy_turns` + GM reaction (fresh correlation id); agent-controlled active
  ⇒ `turn_service.take_turn` + GM reaction (same correlation id, per Plan 8); otherwise
  `None` (the human's turn, or the game/combat is over). Exceptions propagate.
- `apply_input(session, raw) -> InputOutcome`: parse, resolve target over
  `(*party, *enemies)` by id or name, submit the attack command, trigger the GM reaction;
  `say` ⇒ `gm.on_player_say`; unknown target ⇒ recorded, nothing submitted; `DomainError`
  captured as `error`. `/`-commands and empty input are returned unparsed for the caller.

The CLI keeps only rendering, `/commands`, and the REPL itself; its behavior stays
byte-identical (the existing 26-test CLI suite is the gate). Domain layer untouched.

### 4.2 Scenario model (src/evaluation/model.py)

```python
@dataclass(frozen=True)
class ScenarioCheck:
    name: str
    description: str
    evaluate: Callable[[ScenarioResult], bool]

@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    seed: int
    steps: tuple[str, ...]          # human inputs, same grammar the CLI accepts
    repeat_runs: int = 1            # >1 enables cross-run consistency
    checks: tuple[ScenarioCheck, ...]
```

- Steps are strings fed to `apply_input` — `"attack orc brute"`, `"say hold the line"`.
  The runner does not accept `/`-commands (session control is the driver's job).
- Checks are Python predicates over the `ScenarioResult` — deterministic, typed, no YAML.
- `scenarios/__init__.py` exposes `SCENARIOS: Mapping[str, Scenario]` and
  `get_scenario(name)` (raising `EvaluationError` for unknown names).

### 4.3 Run records and results

- `RunRecord` (frozen): `run_index`, `seed`, `event_summaries` (type + key fields per
  event, in order), `invocation_summaries` (`agent_id`, `operation`, `status`, `attempt`,
  `latency_ms`, tokens, cost — never prompts/payloads), `turn_reports`, `party_messages`,
  `duration_ms`.
- `ScenarioResult` (frozen): `scenario`, `provider`, `model`, `runs` (tuple of `RunRecord`),
  `checks` (tuple of `CheckResult(name, description, passed)`), `metrics`
  (`Mapping[str, float | int | None]`), `rejection_reasons` (`Mapping[str, int]`), `status`
  (`"ok" | "error"`), `error` (`str | None`).

### 4.4 Scenarios (three, concrete)

1. **`goblin-skirmish`** — `seed=42`, `repeat_runs=2`, steps:
   `("attack goblin scout", "attack goblin skulker")`. (Amended during planning: the
   original draft repeated `attack goblin scout`, which fails the scenario's own
   no-rejections check under ground truth — the scout dies during step 2's pre-drain
   because the AI party also attacks it, so the second attack is rejected "invalid
   target". Verified offline: both corrected steps are accepted, zero rejections, both
   goblins are defeated.) Checks: **no-rejections** (`rejection_count == 0` — rule
   adherence), **skirmish-enemies-defeated** (both goblin names defeated in every run),
   and **consistent-runs** (cross-run event-type-sequence agreement; offline must be 1.0 —
   this check is what catches harness regressions).
2. **`instruction-following`** — `seed=42`, `repeat_runs=1`, steps:
   `("attack orc brute",)`. (Amended during planning: agents have no instruction channel —
   the human instruction is executed deterministically by the player character — so the
   original "check that the agent's submitted action targets it" was unmeasurable as
   written.) The scenario now measures: (a) **player-attack-fidelity** — every run
   contains an `attack_requested` from Arin targeting Orc Brute (the instruction, executed
   through the rules engine); (b) **agents-attack-enemies** — every run contains at least
   one `attack_requested` from a party agent (Brix/Mira/Sera) naming an enemy-roster
   target: proposals that fail validation surface as `ActionRejected`, covered by the
   **no-rejections** check. Offline (scripted decisions) both hold and validate harness
   plumbing; live, (a) stays a harness check and (b) measures whether the model produces
   legal attack proposals — same scenario, two meanings, stated honestly. Ground truth
   offline: Arin's attack is accepted (a miss), zero rejections.
3. **`cooperation-smoke`** — `seed=42`, `repeat_runs=1`, steps: `("say hold the line",)`,
   GM enabled (fake offline). Checks: **party-messages-exchanged** (at least one party
   message on the board — offline the scripted agents always post one) and
   **no-rejections** (`rejection_count == 0`). Ground truth offline: the `say` triggers a
   GM reaction with no state change; the drain-driven fight produces the party traffic.

### 4.5 Metrics (src/evaluation/metrics.py)

Computed over a `ScenarioResult`; `None` when not computable (never a fake 0 or 1):

- `legal_action_rate`: `AttackRequested / (AttackRequested + ActionRejected[attack_type])`
  averaged over runs; `None` when no attack proposals occurred.
- `rejection_count`: total `ActionRejected`; `rejection_reasons` (its own
  `Mapping[str, int]` field on the result, not a metric value): breakdown by `reason`.
- `retry_count`: invocations with `attempt > 1`.
- `latency_ms_p50`, `latency_ms_p95`: over status-ok invocations.
- `tokens_per_game`: sum of input + output tokens.
- `cost_per_game_usd`: sum of `estimated_cost_usd`; `None` when no priced call occurred.
- `turn_count`: number of turn reports; `party_message_count`: board snapshot size.
- `consistency_agreement`: with `repeat_runs > 1`, the fraction of runs whose event-type
  sequence equals run 0's (offline scripted: must be 1.0 — the check asserts it; live: a
  reported metric, models are not deterministic).

### 4.6 Reporting (src/evaluation/report.py, src/evaluation/cli.py)

- `write_report(result, out_dir) -> Path`: JSON file named
  `<scenario>-<provider>-<model>-<seed>-<UTC timestamp>.json`; contents: scenario
  description, config (no secrets), check results, metrics + rejection reasons, per-run
  event-type sequences, invocation summaries. §34/§50 hold: no API keys, no prompts, no
  payloads, no chain-of-thought.
- `conclave-eval` CLI: `--scenario all|<name>` (default all), `--provider
  fake|openrouter` (default fake), `--seed`, `--repeat N` (overrides the scenario's
  `repeat_runs` when given), `--db memory|postgres`, `--out-dir` (default `eval-results/`,
  created on demand and git-ignored). Prints a Rich
  summary table (scenario, model, runs, checks, legal %, rejections, retries, tokens,
  cost, latency p50/p95, status). Exit codes: 0 all scenarios pass, 1 any check failure or
  error, 2 usage error. `--provider openrouter` without `OPENROUTER_API_KEY` fails fast
  with a clean message before any run.

## 5. Error-handling policy

- Failed check ⇒ recorded as `passed=false` with its description; run continues; exit 1.
- Scenarios are isolated: an exception during a run (live `AgentRuntimeError`, exhausted
  retries, persistence failure) marks that `ScenarioResult` `"error"` with the message and
  the loop moves on — one scenario's failure never blocks the rest (same spirit as
  telemetry never gating the game).
- `EvaluationError` (new, in `src/evaluation/`) for harness-level misuse: unknown scenario,
  unwritable output dir. Domain and application error surfaces are reused, not duplicated.
- Secrets only from the environment; the JSON report never contains them.

## 6. Layer boundaries

- `src/evaluation/` imports `application` + `ai` + reads `domain` event types as data; it
  never imports `interfaces/`, never imports provider SDKs, and mutates game state only
  through application services.
- `src/session/` is a composition root: pure wiring, no rules, no rendering.
- Domain diff invariant (amended): `git log master..HEAD -- src/domain` contains exactly
  one sanctioned commit — Task 1's `roll_initiative` determinism fix. `roll_initiative`
  currently breaks `(total, dexterity_modifier)` ties by `character_id.value`, a random
  uuid4, which violates §47 ("The game engine should be deterministic even when the LLM is
  not") and was observed to make two same-seed sessions diverge in turn order. The fix
  sorts on `(-total, -dexterity_modifier)` only; Python's stable sort preserves
  participant order. No other domain changes are permitted in this plan.
- Within `src/evaluation/`, Rich appears only in `cli.py` (presentation), never in the
  runner or metrics.

## 7. Testing

- Metrics arithmetic: unit tests on synthetic records — rates, sums, percentiles, reason
  breakdowns, `None`-when-not-computable rules.
- Runner end-to-end (offline, scripted gateways): a real session through `build_session`;
  asserts record shape — events, invocation summaries, turn reports, party snapshot all
  populated; errors produce `"error"` status without raising.
- Checks and consistency: identical-seed event-sequence equality and mismatch detection;
  check pass/fail evaluation over a result.
- Session factory + input path: the existing CLI suite (425 tests) must stay green after
  the extraction; new unit tests for `build_session`/`open_session` in `memory` and
  `postgres` modes (pgserver fixtures exist) and for `advance`/`apply_input` dispatch
  (enemy drain, agent turn, attack, say, unknown target).
- `conclave-eval` CLI: exit codes, JSON file naming, table rendering, unknown-scenario and
  missing-API-key errors — all offline.
- No new `live` tests; live evaluation is a manual, env-gated invocation.

## 8. Non-goals (YAGNI)

- No LLM judge or pseudo-judge for decision quality; no memory-relevance or
  information-leakage probes (deferred plan).
- No Postgres persistence of evaluation results; JSON files are the store.
- No committed baselines, no HTML dashboards, no parallel scenario execution.
- No new tools (`tools_called` stays 0); no ruleset, party, or GM behavior changes.
- No OpenTelemetry (deferred per Phase 17's note).

## 9. Plan shape

Task-sized sequence for the implementation plan (TDD throughout):

1. `fix(domain)`: deterministic initiative tie-break in `roll_initiative` (+ tests) — the
   one sanctioned domain change (see §6).
2. `feat(session)`: the `src/session/` composition package (`factory.py` + `play.py`)
   extracted from the CLI; suite stays green, CLI byte-identical.
3. `feat(evaluation)`: scaffolding (errors / model / scenario registry / `goblin-skirmish`)
   + `InMemoryTelemetrySink.invocations()` accessor.
4. `feat(evaluation)`: metrics module with synthetic-record unit tests.
5. `feat(evaluation)`: runner + `goblin-skirmish` end-to-end (offline) — consumes metrics.
6. `feat(evaluation)`: report writer + `eval-results/` gitignore.
7. `feat(evaluation)`: `conclave-eval` CLI + pyproject script entry + exit-code tests.
8. `feat(evaluation)` + `docs`: remaining scenarios (`instruction-following`,
   `cooperation-smoke`) + consistency wiring; README + roadmap row #9 update; full offline
   gate; domain-diff check (except Task 1); live smoke (manual, optional).

## 10. Completion checklist

- [ ] Scenario results are reproducible offline (same seed ⇒ same event sequence).
- [ ] Every numeric metric is traceable to events or enriched invocations.
- [ ] No prompts, payloads, API keys, or reasoning in any report artifact (§34/§50).
- [ ] Evaluation drives only application services; zero rules logic in `src/evaluation/`.
- [ ] Domain diff is exactly Task 1's determinism fix; CLI behavior unchanged; full
      offline suite green.
- [ ] Live mode works with `OPENROUTER_API_KEY` and never runs in CI.