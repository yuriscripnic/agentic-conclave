# Domain-Model & API Contract Document Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the real API/domain-model contract document (`docs/architecture/domain-model-and-api.md`) that Phase 19 (web-api) will implement against — endpoint schemas, DTO shapes, error→HTTP mapping, idempotency semantics, and the persistence model, all derived from the *existing* application services and views.

**Architecture:** Documentation-only plan. No source code changes. The contract is written bottom-up from verified signatures (`GameService`, `AgentTurnService`, `GmDirector`, `GameView`/`TurnReport`/`EventEnvelope`) so the web-api plan can reference it without re-discovery. The current duplicate file `docs/Agentic Conclave-domain-model-and-api.md` is a copy of the architecture overview and stays untouched (it is referenced by the architecture overview doc; the new live document lives at the path the Implementation Plan cites).

**Tech Stack:** Markdown only.

**Spec:** `docs/Agentic Conclave-Implementation Plan.md` §22 (Phase 19) — the contract must cover its route set; §36 table list (persistence model section).

**Roadmap:** resolves the "Known documentation gap" bullet in `docs/superpowers/plans/README.md:40-44`.

## Global Constraints

- No code changes: `git status` shows only the new doc and the README status flip.
- Every signature/field listed must be **copied verbatim from source** and verified by the checking command in Task 2 — no aspirational APIs.
- The document must not invent rules: CLAUDE.md §40–41 constraints (routes don't roll dice, DTOs are separate from domain models) are stated as contract rules.
- Line length is irrelevant for docs, but tables use the repo's existing doc style (see `docs/Agentic Conclave-architecture-overview.md`).

## File Structure

| File | Responsibility |
|---|---|
| `docs/architecture/domain-model-and-api.md` | The contract: API surface, DTO schemas, error map, idempotency, persistence model |
| `docs/superpowers/plans/README.md` | Status table flip (gap resolved) |

---

### Task 1: Write the contract document

**Files:**
- Create: `docs/architecture/domain-model-and-api.md`

**Interfaces:**
- Produces: the authoritative sections the web-api plan cites — §1 Domain views (DTO source-of-truth), §2 HTTP surface, §3 Error→HTTP map, §4 Idempotency, §5 Persistence model.

- [ ] **Step 1: Verify the signatures you are about to document**

Run:

```bash
grep -n "def create_game\|def submit_action\|def get_view\|def get_events" src/application/game_service.py
grep -n "def take_turn" src/application/agents/agent_turn_service.py
grep -n "def on_player_say\|def on_turn_report" src/application/gm/director.py
grep -n "class GameView\|class TurnReport\|class CharacterView\|class CombatView" src/application/views.py
```

Expected: signatures match the tables below. If any mismatch, correct the doc content before writing.

- [ ] **Step 2: Write the document**

Create `docs/architecture/domain-model-and-api.md` with exactly these sections (full skeleton; complete the prose where marked):

```markdown
# Domain Model & API Contract

Source of truth for the web API (Phase 19 bind: plans #10). Derived from the
application layer as implemented; the API adapts it, never redefines it.

## 1. Domain views (application layer → DTO source)

HTTP DTOs in `src/interfaces/api/dto.py` mirror these frozen dataclasses
field-for-field. The API layer must not reshape, merge, or extend them.

| View | Fields | Source |
|---|---|---|
| `CharacterView` | `id, name, character_class (str|None), level, hp_current, hp_max, armor_class, conditions (list[str]), is_defeated` | `src/application/views.py` |
| `InitiativeEntryView` | `character_id, name, total` | `src/application/views.py` |
| `CombatView` | `round_number, status, active_actor_id (str|None), initiative_order` | `src/application/views.py` |
| `GameView` | `game_id, campaign_name, status, party, enemies, combat (CombatView|None)` | `src/application/views.py` |
| `TurnReport` | `game_id, accepted, error_code, reason, events (list[EventEnvelope]), view, game_over` | `src/application/views.py` |
| `AgentTurnReport` | `actor_id, actor_name, accepted, proposal_source, action_attempts, rejection_reasons, fallback_reason, public_message, invocations, turn_report, party_message (str|None), memory_retrieved` | `src/application/agents/agent_turn_service.py` |
| `EventEnvelope` | `sequence, event_id, game_id, occurred_at, event_type, payload (dict)` | `src/domain/events/collector.py` |
| `GmResult` | `narration, npc_reply, addressed_to (str|None)` | `src/application/gm/director.py` |
| `PartyMessage` | `actor_name, text, round_number` | `src/application/agents/party_board.py` |

## 2. HTTP surface (GET /api/v1)

Contract rules (from CLAUDE.md §40–41):

1. Routes validate HTTP input, construct commands, invoke application services, map results to DTOs — nothing else.
2. No dice, damage, HP, or rules logic in route handlers.
3. `GameId`/`CharacterId` are opaque strings in JSON.

| Route | Method | Request body | Response DTO | Calls |
|---|---|---|---|---|
| `/api/v1/games` | POST | `CreateGameRequest {campaign_name?: str = "The Forgotten Ruins", seed?: int}` (header `Idempotency-Key`) | `201 SessionResponse` → POST creates a full session via `session.build_session` and returns `SessionResponse {game_id, view: GameView, opening_narration: str|None}` | `session.factory.build_session(SessionConfig(...))` |
| `/api/v1/games/{game_id}` | GET | — | `200 GameViewResponse` | `GameService.get_view` |
| `/api/v1/games/{game_id}/status` | GET | — | `200 GameStatusResponse {status, combat: CombatView|None, game_over}` | `GameService.get_view` |
| `/api/v1/games/{game_id}/events` | GET | — | `200 {events: list[EventEnvelopeResponse]}` | `GameService.get_events` |
| `/api/v1/games/{game_id}/input` | POST | `InputRequest {text: str}` (header `Idempotency-Key`) — `text` is `"attack <target>"` or `"say <text>"`, parsed exactly as the CLI parses it | `200 InputResponse {report: TurnReportResponse, gm: GmResponse|None}` | `session.play.apply_input` then `GmDirector.on_turn_report` / `on_player_say` |
| `/api/v1/games/{game_id}/actions` | POST | `ActionRequest {action_type: str, target_id?: str, weapon_id?: str}` (header `Idempotency-Key`) | `200 TurnReportResponse` | `GameService.submit_action(SubmitActionCommand(game_id, actor=active_actor_id, ...))` |

Notes:
- `actor_id` for `/actions` and `/input` is always the actor at `view.combat.active_actor_id`; the API resolves the target by id or case-insensitive name exactly as `session/play.py:apply_input` does — no second parser is written.
- Agent/driven turns remain the client's responsibility: the server does not auto-advance and never spawns background turns in Phase 19.
- No parties/campaigns CRUD in Phase 19 — one game = one session (Implementation Plan §22 route set lists campaigns; campaigns remain a stub root documented as 501).

## 3. Error → HTTP map

All expected failures are handled by exception handlers in
`src/interfaces/api/errors.py`; unknown exceptions → `500 {"error": "internal_error"}`
(without stack trace details).

| Exception | Module | HTTP | Error code |
|---|---|---|---|
| `GameNotFoundError` | `domain/common/errors.py` | 404 | `game_not_found` |
| `CharacterNotFoundError` | `domain/common/errors.py` | 404 | `character_not_found` |
| `ValidationError` | `domain/common/errors.py` | 422 | `validation_error` |
| `InvalidActionError` | `domain/common/errors.py` | 422 | `invalid_action` |
| `NotYourTurnError` | `domain/common/errors.py` | 409 | `not_your_turn` |
| `ActionNotAvailableError` | `domain/common/errors.py` | 409 | `action_not_available` |
| `CombatNotActiveError` | `domain/common/errors.py` | 409 | `combat_not_active` |
| `InsufficientResourceError` | `domain/common/errors.py` | 422 | `insufficient_resource` |
| `GameNotRunningError` | `domain/common/errors.py` | 409 | `game_not_running` |
| `AgentDecisionFailedError` | `domain/common/errors.py` | 502 | `agent_decision_failed` |
| `ConcurrentGameModification` | `domain/common/errors.py` | 409 | `concurrent_modification` |
| `PersistenceError` | `domain/common/errors.py` | 503 | `persistence_error` |
| `AgentNotRegisteredError` (KeyError) | `application/agents/agent_turn_service.py` | 409 | `agent_not_registered` |
| `ModelError` family | `ai/models/errors.py` | 502 | `model_error` |
| `InvalidGmResponseError` | `application/gm/director.py` | 502 | `gm_invalid_response` |

Body shape for all handled errors: `{"error": "<code>", "reason": "<message>"}`.

## 4. Idempotency

- Applies to the three state-changing routes: `POST /games`, `/input`, `/actions`.
- `Idempotency-Key: <string>` header; a repeat request with the same key on the same route+game must return the first response without re-executing.
- Storage: in-process dict keyed by `(route, game_id|None, idempotency_key)`; first response DTO is cached (headers omitted). Collision semantics are fire-and-reuse, not strong serialization.
- Without a key: no dedup (documented, not an error).

## 5. Persistence model

Authoritative table list: CLAUDE.md §36. Implemented today (migrations 001–003):
`games`, `game_events`, `llm_invocations`; memory tables via pgvector repository.
Candidate tables not yet implemented remain listed with a "not implemented" note —
the contract must not imply they exist. See
`src/infrastructure/persistence/postgres/migrations/` for column truth.

## 6. Process model note

`GameService` holds combat state, dice, and event collectors in memory
per-process (`_combats`, `_dice`, `_collectors`); `PartyMessageBoard`,
`GmConversation` likewise. Phase 19 therefore runs single-process (uvicorn,
workers=1) and keeps a `GameSession` registry keyed by `game_id`. Extraction to
a stateless service is a future decision, not part of this contract.
```

- [ ] **Step 3: Routing sanity check against existing CLI behavior**

Run the CLI once in fake mode to confirm the documented flows are reachable (optional but recommended):

```bash
echo "attack first_living_opponent" | .venv/bin/python -m interfaces.cli.app --agent fake --gm off
```

(If direct module invocation fails under strict sh, use the worktree-smoke pattern from the observability plan: write input to `/tmp/input.txt` and pipe via `python -c`.) Expected: session opens, combat starts, `attack` resolves — confirming §2's documented call-flow matches reality.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/domain-model-and-api.md
git commit -m "docs: add domain model and API contract document"
```

---

### Task 2: Flip the roadmap gap + self-review checklist

**Files:**
- Modify: `docs/superpowers/plans/README.md:38-44`

**Interfaces:**
- Produces: web-api plan (#10) may now cite `docs/architecture/domain-model-and-api.md` as spec.

- [ ] **Step 1: Update the README gap bullet**

Replace the gap bullet with:

```markdown
- Resolved (pre-Plan 10): the API/domain-model contract lives at
  `docs/architecture/domain-model-and-api.md` (endpoint schemas, DTO shapes,
  error→HTTP map, idempotency, persistence model). Plan 10 *web-api* argues from it.
```

- [ ] **Step 2: Coverage self-review**

Verify against the Implementation Plan §22 route list and the source:

```bash
grep -c "api/v1" docs/architecture/domain-model-and-api.md   # ≥ 6 (all §22 routes covered)
grep -n "get_view\|submit_action\|get_events" docs/architecture/domain-model-and-api.md | wc -l
```

Confirm every table row's field list matches source (re-run Task 1 Step 1's greps). Confirm no prose claims a middleware, auth, or pagination feature — none are implemented.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/README.md
git commit -m "docs: mark API contract gap resolved in roadmap"
```
