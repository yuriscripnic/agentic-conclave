# Evaluation Design — Phase 18 (Roadmap Plan #9)

Date: 2026-09-10
Status: Approved (design sections approved in session; see git history)
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
   wiring is extracted into an application-layer composition root that the CLI, the
   evaluation harness, and the future API layer (Plan 10) all share — §63's shared-contract
   rule, paid forward.

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
build_session(SessionConfig) (src/application/session.py)   ← shared with CLI, later API
  ↓  per step: human input → apply_input() → AgentTurnService / GmDirector
  ↓  (one correlation_id per step, per Plan 8)
EventRepository + InMemoryTelemetrySink + turn reports + PartyMessageBoard
  ↓
EvalRunRecord → metrics.py → checks → report.py → JSON file + console table
```

Evaluation contains **no game rules** and never mutates game state except through
application services — the same path the CLI drives (§71 invariant: LLMs propose, the
domain decides).

### 4.1 Session factory and shared input path (src/application/session.py)

A composition root, extracted from the CLI with contracts preserved:

- `SessionConfig` (frozen dataclass): `seed`, `db` (`"memory" | "postgres"`),
  `database_url` (`str | None`), `agent_mode` (`"fake" | "llm"`), `gm_mode`
  (`"off" | "llm" | "fake"`), `gateway` (`ModelGateway | None` — injectable for scripted /
  eval / test use), `provider` (`str | None` — used only when `gateway` is `None`).
- `GameSession` (frozen dataclass): `game_service`, `turn_service`, `gm_director`
  (`GmDirector | None`), `events` (event repository), `telemetry` (`TelemetrySink`).
- `build_session(config) -> GameSession`: builds repositories (memory or Postgres via
  `DATABASE_URL` semantics already established), party agents, GM director, telemetry
  plumbing — moving the bodies of `build_service` / `_wire_party` / `_wire_gm`.
- `apply_input(session, raw: str)` — the CLI loop's engine moved to the application layer:
  parse (`parse_input` moves here), resolve target, submit the action command, advance
  agent/enemy turns, trigger the GM reaction, returning outcome data for the caller to
  render. The CLI keeps only rendering, `/commands`, and the REPL itself.
- Domain layer untouched; CLI behavior byte-identical (existing suite is the gate).

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

1. **`goblin-skirmish`** — `seed=42`, `repeat_runs=2`, steps: two `attack` instructions
   against the skirmish enemy. Checks: no `ActionRejected` (rule adherence), enemy
   defeated, and cross-run event-type-sequence consistency (offline: must be identical;
   this check is what catches harness regressions).
2. **`instruction-following`** — an attack instruction naming a specific target; check that
   the agent's submitted action targets it. Offline (scripted decision canned to match the
   instruction) this validates harness plumbing; live it measures the model — same
   scenario, two meanings, stated honestly.
3. **`cooperation-smoke`** — full party, a `say` instruction; checks that party messages
   occurred and no action was rejected.

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
- `src/application/session.py` is a composition root: pure wiring, no rules, no rendering.
- Domain diff invariant: `git log master..HEAD -- src/domain` stays empty for this plan.
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
  the extraction; new unit tests for `build_session` in `memory` and `postgres` modes
  (pgserver fixtures exist) and for `apply_input` dispatch (attack / say / unknown).
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

1. Session factory + shared input path extraction (CLI refactor, suite stays green).
2. Evaluation package scaffolding: model + registry + `goblin-skirmish` + runner (offline).
3. Metrics module with synthetic-record unit tests.
4. Report writer + `eval-results/` gitignore.
5. `conclave-eval` CLI + pyproject script entry + exit-code tests.
6. Remaining scenarios (`instruction-following`, `cooperation-smoke`) + consistency.
7. README + roadmap row #9 update; full offline gate; live smoke (manual, optional).

## 10. Completion checklist

- [ ] Scenario results are reproducible offline (same seed ⇒ same event sequence).
- [ ] Every numeric metric is traceable to events or enriched invocations.
- [ ] No prompts, payloads, API keys, or reasoning in any report artifact (§34/§50).
- [ ] Evaluation drives only application services; zero rules logic in `src/evaluation/`.
- [ ] Domain diff empty; CLI behavior unchanged; full offline suite green.
- [ ] Live mode works with `OPENROUTER_API_KEY` and never runs in CI.