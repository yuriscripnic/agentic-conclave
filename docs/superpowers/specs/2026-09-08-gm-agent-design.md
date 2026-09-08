# GM Agent Design (Plan 5 — Phase 13)

Status: approved for implementation planning (user-approved design sections, 2026-09-08).
Builds on: Plans 3/4/5/6 — `ModelGateway`, `AgentRuntime` structured decisions,
`AgentTurnService`, `PartyMessageBoard`, `MemoryService`.
Roadmap: `docs/superpowers/plans/README.md` row 5 (Phase 13).

## 1. Goal

Add the Game Master as an **AI narrator and NPC voice** for the existing CLI game:

- scene-setting narration when combat opens;
- short reactions to **notable** turn events (critical hits, defeats, combat end);
- in-character NPC replies when the player types `say <text>`.

The GM never mutates game state, never rolls dice, and never blocks the game:
it observes what the rules engine already did and speaks about it.

## 2. Decisions

- **D1 — Scope.** Narration + NPC talk only. Encounter initiation, quest
  progression, world consequences, and story orchestration stay deferred
  (roadmap Implementation Plan doc lists them under Phase 13; they need domain
  concepts that do not exist yet). Non-goals in §6.
- **D2 — Mechanism: structured output, no tool layer.** The GM decides through
  the existing `AgentRuntime.decide_structured(profile, system, user, schema)`
  — the same pattern as character agents. This plan's GM proposes nothing that
  mutates state, so the `AgentTool`/`AgentToolExecutor` abstractions (§7/§31)
  debut with world consequences in a later plan, not here.
- **D3 — Cadence: hook-driven, notable events only.** GM LLM calls happen at
  exactly three kinds of moments: combat open, a turn report containing at
  least one notable event, and `say`. ~2–4 GM calls per typical fight.
  Reports with no notable event cost **zero** LLM calls.
- **D4 — Notable events.** `attack_resolved` with `critical == true`;
  `character_defeated`; `combat_ended`. Plain hits/misses, initiative, turn
  markers, and `action_rejected` are never narrated.
- **D5 — Talk targets: enemies as personas.** `say <text>` addresses the
  scene; the GM picks the most fitting **living enemy** as the respondent and
  names it in `addressed_to` (its name/stats act as the persona), or narrates
  without an addressee if none fits. Zero domain changes — no NPC entity.
  Non-combatant NPC entities are **explicitly future work** (user decision
  2026-09-08: "add npc later in the project").
- **D6 — Architecture: `GmDirector` application service, hook-called by the
  interface.** The CLI loop (and any future API/Web adapter) calls the director
  at the hooks. The game engine, `GameService`, and `src/domain/` stay LLM-free
  and unchanged; the dependency direction matches `AgentTurnService` (§63:
  CLI/Web/API share application contracts).
- **D7 — Context engineering is a dedicated concern (§22).** A single context
  builder assembles every GM prompt: system prompt = persona + hard rules; user
  prompt = scene roster + event digest + recent conversation + a task marker
  (`narrate_open` | `react_to_events` | `respond_to_player`). System-prompt hard
  rules: restate only what the digest and scene view contain; never invent dice
  results, HP, or outcomes; never propose game actions; keep it short.
- **D8 — One response schema, cosmetic cleanup never rejects.**
  `GM_RESPONSE_SCHEMA = {narration: string, npc_reply: string | null,
  addressed_to: string | null}`. Mapping collapses whitespace and truncates to
  configured caps (like the character agent's `memory_note`, spec §3.4 spirit):
  a bad string is never a game rejection because there is no game action.
- **D9 — Mode flag, offline by default.** `--gm off|llm|fake`, **default
  `fake`** (project norm: deterministic offline defaults). Orthogonal to
  `--agent`: `--agent llm --gm fake` is valid. `llm` uses the existing
  `[profiles.gm]` entry in `llm.toml` (temperature 0.8, max_tokens 1024) — its
  first consumer.
- **D10 — Failure policy: the GM never gates the game.** Any `ModelError` or
  unmappable structured response yields an empty `GmResult` (all narrative
  fields `None`) with the failed `LLMInvocation` attached for telemetry; the
  interface prints nothing. The transient-retry budget is `AgentRuntime`'s
  existing `RetryPolicy`; there is no rules-feedback retry loop because there
  is no rules validation to fail. GM conversation history is in-RAM per game
  (like `PartyMessageBoard`) and is not persisted in this plan.

## 3. Components

### 3.1 `src/application/gm/profiles.py` — `GmProfile` + loader

```python
@dataclass(frozen=True)
class GmProfile:
    name: str                  # e.g. "The Dungeon Master"
    style: str                 # persona/style directive(s)
    narration_max_chars: int   # default 280
    reply_max_chars: int       # default 200
    history_limit: int         # default 12
```

`load_gm_profile(path) -> GmProfile` reads **`config/gm.toml`** (new file,
`[gm]` section) with validation errors following the `agents.toml` loader
conventions (explicit `ProfileConfigError`-style failures, no silent defaults
beyond the caps above). No `llm.toml` changes.

### 3.2 `src/application/gm/conversation.py` — `GmConversation`

In-RAM board mirroring `PartyMessageBoard`: unbounded appends, bounded reads.

```python
@dataclass(frozen=True)
class GmMessage:
    speaker: str   # "player" | "gm" | the NPC name
    text: str

class GmConversation:
    def append(self, message: GmMessage) -> None: ...
    def recent(self, limit: int) -> tuple[GmMessage, ...]: ...   # limit <= 0 -> ()
```

### 3.3 `src/application/gm/director.py` — `GmDirector` + `GmResult`

```python
@dataclass(frozen=True)
class GmResult:
    narration: str | None = None
    npc_reply: str | None = None
    addressed_to: str | None = None
    invocations: tuple[LLMInvocation, ...] = ()

class GmDirector:
    def __init__(self, game_service, runtime, model_catalog, profile,
                 conversation: GmConversation) -> None: ...
    def on_combat_open(self, game_id: GameId) -> GmResult: ...
    def on_turn_report(self, game_id: GameId, report: TurnReport) -> GmResult | None: ...
    def on_player_say(self, game_id: GameId, text: str) -> GmResult: ...
```

- `on_combat_open` — builds scene context + `narrate_open` task; returns the
  opening narration (empty `GmResult` on failure).
- `on_turn_report` — extracts the event digest **first**; `None` (no call, no
  result) when no notable event is present (D3/D4).
- Hooks that arrive without a `TurnReport` (`on_combat_open`, `on_player_say`)
  take their scene view from `self._game_service.get_view(game_id)`;
  `on_turn_report` uses `report.view`.
- `on_player_say` — appends the player's line to the conversation, builds
  scene + history context + `respond_to_player` task; appends `gm`/NPC reply
  entries after a successful call. Works in and out of combat; with no living
  enemies the GM still narrates (`addressed_to=None`).

`model_catalog.get("gm")` supplies the model profile; the `AgentRuntime`
instance is injected (the CLI reuses the same runtime/gateway wiring style as
the party — a separate `AgentRuntime(gateway, RetryPolicy())` for the GM).

### 3.4 Context builder (`director.py`-internal, dedicated function, §22)

`build_gm_context(profile, view, digest, history, task) -> tuple[str, str]`
(system, user). Digest lines are plain text derived from `TurnReport.events`
(event type + character names + outcome — not the Rich renderer's strings).
The user prompt renders, in order: task marker, scene roster (names, classes,
HP fractions, defeated flags), digest lines, conversation history
(`speaker: text`), instruction line. Nothing outside the view + events +
conversation enters the prompt (§20).

### 3.5 Schema + mapping (`director.py`)

`GM_RESPONSE_SCHEMA` per D8. `map_gm_response(data, profile) -> tuple[str | None, str | None, str | None]`
collapses internal whitespace, truncates `narration`/`npc_reply` to
`narration_max_chars`/`reply_max_chars`, drops `addressed_to` that does not
name a living enemy in the scene, and returns `None` fields for silence.
Failures raise one local error (`InvalidGmResponseError`) which the director
converts to an empty `GmResult` (D10) with the invocation recorded.

### 3.6 CLI wiring (`interfaces/cli/app.py`, `renderer.py`)

- `--gm off|llm|fake`, default `fake`; wired alongside `--agent`
  (same `OPENROUTER_API_KEY` gate for `llm`).
- `parse_input` gains `("say", text)` for `say <text>`.
- Loop integration: after `start_combat` → `on_combat_open`; after each
  rendered turn report (player, agent, enemy) → `on_turn_report`; on `say` →
  `on_player_say`. All GM output renders through a new
  `render_gm_result(console, result, view)` in `renderer.py` (GM lines styled
  distinctly, e.g. italic dim); failures print nothing.
- The `say` verb works regardless of whose turn it is and never submits a
  game action.

### 3.7 Fake mode (`application/agents/fake_script.py`)

`ScriptedGmGateway(inner: FakeModelGateway, decision: Callable[[str], Mapping])`
mirrors `ScriptedAgentGateway`: re-enqueues a canned response before every
call; the callable receives the user prompt so it can key off the task marker
and return deterministic narration/replies. `--agent fake --gm fake` therefore
demos the full flow offline (§46).

## 4. Failure table

| Failure | Detection | Behavior |
|---|---|---|
| Model transport/timeout/rate-limit | `ModelError` from runtime after retries | Empty `GmResult`, invocation recorded, nothing printed, game continues |
| Malformed/empty structured response | `InvalidGmResponseError` in mapping | Empty `GmResult`, invocation recorded, nothing printed |
| Report has no notable events | Digest scan | `on_turn_report` returns `None`; zero LLM calls |
| `say` with no living enemies | Scene scan | GM narrates, `addressed_to=None` |
| `--gm llm` without `OPENROUTER_API_KEY` | CLI wiring | Same error path as `--agent llm` (message + exit 2) |
| Unknown `--gm` value | argparse | Standard argparse rejection |
| Config `gm.toml` invalid | Loader validation | Explicit config error at wire time (no silent defaults) |

## 5. Test list (all offline unless noted)

1. `GmConversation`: append, `recent(n)`, limit eviction, `limit <= 0` → `()`.
2. Digest extraction from synthetic `TurnReport`s: critical hit, defeat,
   combat_end are notable; plain hit/miss/turn/initiative/rejected are not.
3. Context builder: contains task marker, scene roster, digest lines, history;
   contains nothing outside view + events + conversation (§20 leak check).
4. `map_gm_response`: truncation to caps, whitespace collapse, null fields,
   `addressed_to` dropped unless a living enemy matches.
5. Director via `FakeModelGateway`: opening narration call; **no LLM call when
   the report has nothing notable**; say flow appends both sides to the
   conversation and returns `npc_reply`; model failure → empty `GmResult` with
   invocation recorded.
6. CLI: `parse_input` recognizes `say`; offline `--agent fake --gm fake` run
   shows opening narration and an NPC reply; GM failure paths print nothing
   (`GmResult.invocations` remains inspectable for tests/debug).
7. Config loader: valid `config/gm.toml` loads; missing/invalid fields raise
   explicit config errors.

## 6. Non-goals (deferred)

- `AgentTool`/`AgentToolExecutor` tool layer (arrives with world consequences).
- Encounter initiation, quest progression, world consequences, story
  orchestration (need new domain concepts first).
- Non-combatant NPC entities (user decision 2026-09-08: later in the project).
- GM conversation persistence (in-RAM now, like `PartyMessageBoard`).
- Targeted/whisper messages; GM memory integration (the GM could adopt
  `MemoryService` in a later plan).
- GM-driven combat rulings or dice (never — §2.1).

## 7. Global constraints

- `src/domain/` diff vs master: **empty**. All code lives in
  `src/application/gm/`, `src/application/agents/fake_script.py`,
  `src/interfaces/cli/`, `config/gm.toml`, tests.
- Offline by default: the full suite passes with no `OPENROUTER_API_KEY`.
- No provider names or SDK imports outside `src/infrastructure/llm/`.
- No secrets in config; key from `OPENROUTER_API_KEY` env only.
- No hidden chain-of-thought anywhere (§33); GM output is ordinary model text.
- Memory contents / GM conversation never logged or persisted (§20, §34).
- Conventional commits scoped by layer (`feat(application): ...`,
  `feat(interfaces): ...`, `test(...)`); every task TDD; gate = ruff + mypy
  strict + pytest.

## 8. Completion checklist

- [ ] Domain untouched; `git log master..HEAD -- src/domain` empty.
- [ ] GM calls happen only at the three hook kinds; no-call path proven by test.
- [ ] GM failures never fail a turn, block input, or mutate state.
- [ ] `--agent fake --gm fake` demos narration + say fully offline.
- [ ] `--gm llm` works against OpenRouter using `[profiles.gm]` (optional live check).
- [ ] No LLM call for non-notable reports (D3/D4).
- [ ] Full suite green; ruff + mypy strict clean; telemetry invocations recorded.
- [ ] README gains a short "The Game Master" section.
