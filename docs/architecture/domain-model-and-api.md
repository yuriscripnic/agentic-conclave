# Domain Model & API Contract

Source of truth for the web API (Phase 19, plans row #10). This document is
written bottom-up from the application layer as implemented; the API adapts it,
never redefines it. Plan: `docs/superpowers/plans/2026-09-13-web-api.md`.

## 1. Domain views (application layer → DTO source of truth)

HTTP DTOs in `src/interfaces/api/dto.py` mirror these frozen dataclasses
field-for-field. The API layer must not reshape, merge, or extend them
(`CLAUDE.md` §41: HTTP DTO ≠ Application Command ≠ Domain Model ≠ Persistence
Model).

| View | Fields | Source |
|---|---|---|
| `CharacterView` | `id, name, character_class (str|None), level, hp_current, hp_max, armor_class, conditions (list[str]), is_defeated` | `src/application/views.py` |
| `InitiativeEntryView` | `character_id, name, total` | `src/application/views.py` |
| `CombatView` | `round_number, status, active_actor_id (str|None), initiative_order` | `src/application/views.py` |
| `GameView` | `game_id, campaign_name, status, party, enemies, combat (CombatView|None)` | `src/application/views.py` |
| `TurnReport` | `game_id, accepted, error_code, reason, events (list[EventEnvelope]), view, game_over` | `src/application/views.py` |
| `AgentTurnReport` | `actor_id, actor_name, accepted, proposal_source, action_attempts, rejection_reasons, fallback_reason, public_message, invocations, turn_report, party_message (str|None), memory_retrieved` | `src/application/agents/agent_turn_service.py` |
| `EventEnvelope` | `sequence, event_id, game_id, occurred_at, event_type, payload (dict[str, object])` | `src/domain/events/collector.py` |
| `GmResult` | `narration, npc_reply, addressed_to (str|None)` | `src/application/gm/director.py` |
| `PartyMessage` | `actor_name, text, round_number` | `src/application/agents/party_board.py` |

`Status` values are lowercase `StrEnum` values from `src/domain/world/game.py`
(`created`, `running`, `ended`) and combat status from
`src/domain/combat/combat.py` the same way.

## 2. HTTP surface (`/api/v1`)

Contract rules (`CLAUDE.md` §40–41):

1. Routes validate HTTP input, construct commands, invoke application services,
   and map results to DTOs — nothing else.
2. No dice, damage, HP, AC, initiative, or rule logic in route handlers.
3. `game_id` / `character_id` are opaque strings on the wire.
4. One parser: human input is classified by the *same* `parse_input`/`apply_input`
   code the CLI uses (`src/session/play.py`); the API is a second adapter over it
   (`§63`), and no second parser is written.

| Route | Method | Request body | Response DTO (200/201) | Application call |
|---|---|---|---|---|
| `/api/v1/games` | POST | `CreateGameRequest {campaign_name?: str = "The Forgotten Ruins", seed?: int}` + `Idempotency-Key` header | `201 SessionResponse {game_id, view: GameViewResponse, opening: GmResponse|null}` | `session.factory.build_session(SessionConfig(...))`, then `GmDirector.on_combat_open` |
| `/api/v1/games/{game_id}` | GET | — | `200 GameViewResponse` | `GameService.get_view` |
| `/api/v1/games/{game_id}/status` | GET | — | `200 StatusResponse {status, combat: CombatResponse|null, game_over}` | `GameService.get_view` |
| `/api/v1/games/{game_id}/events` | GET | — | `200 {"events": list[EventEnvelopeResponse]}` | `GameService.get_events` |
| `/api/v1/games/{game_id}/input` | POST | `InputRequest {text: str}` + `Idempotency-Key` header — `text` is `"attack <target>"` or `"say <text>"`, classified exactly like the CLI | `200 InputResponse {kind, report: TurnReportResponse|null, gm: GmResponse|null}` | `session.play.apply_input`, then `GmDirector.on_player_say` / `on_turn_report` |
| `/api/v1/games/{game_id}/actions` | POST | `ActionRequest {action_type: str, target?: str, weapon_id?: str}` (target = id or case-insensitive name) + `Idempotency-Key` header | `200 TurnReportResponse` | `GameService.submit_action(SubmitActionCommand(game_id, actor=active_actor_id, ...))` |
| `/api/v1/health` | GET | — | `200 {"status": "ok"}` | none |
| `/api/v1/campaigns` | — | — | `501` in Phase 19 (stub; see roadmap gap below) | — |

Notes:

- `actor_id` is always the actor at `view.combat.active_actor_id`; the route
  resolves the target id/name exactly as `session/play.py:apply_input` does.
- Agent/enemy turns are the client's responsibility: the server never auto-runs
  turns in Phase 19. The CLI loop (`advance`, `run_active_enemy_turns`,
  `AgentTurnService.take_turn`) remains the reference implementation for a future
  `/turns` route — out of scope here.

## 3. Error → HTTP map

All expected failures are handled by exception handlers in
`src/interfaces/api/errors.py`. Unlisted `DomainError` → 409 `domain_error`;
anything else → 500 `internal_error` (no stack-trace leakage).

| Exception | Module | HTTP | Error code |
|---|---|---|---|
| `GameNotFoundError` | `domain/common/errors.py` | 404 | `game_not_found` |
| `CharacterNotFoundError` | `domain/common/errors.py` | 404 | `character_not_found` |
| `ValidationError` | `domain/common/errors.py` | 422 | `validation_error` |
| `InvalidActionError` | `domain/common/errors.py` | 422 | `invalid_action` |
| `InsufficientResourceError` | `domain/common/errors.py` | 422 | `insufficient_resource` |
| `NotYourTurnError` | `domain/common/errors.py` | 409 | `not_your_turn` |
| `ActionNotAvailableError` | `domain/common/errors.py` | 409 | `action_not_available` |
| `CombatNotActiveError` | `domain/common/errors.py` | 409 | `combat_not_active` |
| `GameNotRunningError` | `domain/common/errors.py` | 409 | `game_not_running` |
| `AgentDecisionFailedError` | `domain/common/errors.py` | 502 | `agent_decision_failed` |
| `ConcurrentGameModification` | `domain/common/errors.py` | 409 | `concurrent_modification` |
| `PersistenceError` | `domain/common/errors.py` | 503 | `persistence_error` |
| `ModelError` (+ subclasses) | `ai/models/errors.py` | 502 | `model_error` |
| `InvalidGmResponseError` | `application/gm/director.py` | 502 | `gm_invalid_response` |
| `DomainError` (fallback) | `domain/common/errors.py` | 409 | `domain_error` |

Body shape for all handled errors: `{"error": "<code>", "reason": "<message>"}`.

## 4. Idempotency

- Applies to the three state-changing routes: `POST /games`, `/input`, `/actions`
  (`CLAUDE.md` §39).
- `Idempotency-Key: <string>` header; a repeat request with the same key on the
  same logical scope (route +, where relevant, game) must return the first
  response payload without re-executing, with the same HTTP status as first
  execution.
- Storage: in-process dict keyed `(key, scope)`; scopes are `"POST /games"`,
  `f"games/{game_id}/actions"`, `f"games/{game_id}/input"`. First-response DTO is
  cached via `model_dump()`.
- No key header: no dedup — the empty key is a documented no-op, not an error.

## 5. Persistence model

Authoritative table list: `CLAUDE.md` §36. Implemented today (migrations
001–003 under `src/infrastructure/persistence/postgres/migrations/`): `games`,
`game_events`, `llm_invocations`; agent memories via the pgvector repository
(`infrastructure/memory/pgvector_repository.py`). The §36 candidate tables not
yet implemented (campaigns, quests, inventory, …) are *not* part of the current
persistence model and must not be implied as available in Phase 19.

Transactions: a single optimistic-locked transaction per save inside
`PostgresGameRepository.save` (`UPDATE ... WHERE version`, rowcount 0 →
`ConcurrentGameModification`), events appended atomically in the same commit.

## 6. Process model (Phase 19 constraint)

`GameService` holds combat state, the seeded dice roller, and event collectors
in memory per process (`_combats`, `_dice`, `_collectors`); `PartyMessageBoard`,
`GmConversation`, and the idempotency cache are likewise per-process. Phase 19
therefore runs **single-process** (uvicorn, `workers=1`) and keeps a
`SessionRegistry` mapping `game_id → GameSession` in that process; a per-game
`threading.Lock` serializes state-changing requests within it. Extraction to a
stateless/clustered model is a future decision, not part of this contract.
