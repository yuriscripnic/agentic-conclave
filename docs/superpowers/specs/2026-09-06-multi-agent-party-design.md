# Multi-Agent Party Design (Plan 5)

**Status:** Approved design → spec
**Date:** 2026-09-06
**Phase:** 9 (multi-agent party; first slice of §32 communication)
**References:** `CLAUDE.md` (§7, §17, §20, §22, §28, §32, §45–46, §48, §65), `docs/superpowers/specs/2026-09-05-character-agent-design.md` (binding for the decision pipeline, retry budgets, and fallback this plan extends)

---

## 1. Purpose

Plan 4 proved the decision pipeline with one agent (Brix). Plan 5 turns the single-agent
demo into a genuine multi-agent party: **three AI-controlled party members alongside the
human's Arin**, fighting a three-enemy encounter, with a first slice of party communication
(§32) so the agents coordinate through what they actually say — not through hidden state.

The invariant is unchanged: **the LLM proposes, the domain decides, the engine executes,
events record.** Nothing in this plan touches `src/domain/`. No new LLM call per turn —
each agent still spends exactly one decision call (plus bounded retries) per turn.

## 2. Decisions

1. **Party + comms scope (Approach 1: extend the Plan 4 stack).** Config-driven N-agent
   party, a richer encounter, and broadcast party chatter via an optional field on the
   existing decision. No `AgentScheduler` component — the initiative loop in the CLI
   already dispatches every active actor, and `AgentTurnService` already serves any
   registered actor, so "multi-agent" is mostly configuration plus the message board.
   The scheduler abstraction waits for a second interface consumer (Phase 11).
2. **Three AI characters + Arin.** Brix (fighter, existing persona), **Mira** (rogue:
   opportunistic — finishes wounded foes, picks her shots), **Sera** (cleric: protective —
   watches the party's backs, calls out threats). Classes change statline, weapon, and
   persona only; actions stay attack-only until the engine resolves more actions. The
   class fantasy lives in the prompt.
3. **Encounter: two goblins + an orc.** Goblin Scout, Goblin Skulker, Orc Brute — distinct
   names, because the CLI resolves human targets by name and duplicates would collide. A
   target-priority problem (boss vs minions) gives the agents something real to coordinate
   about. Enemy turns remain deterministic engine AI — more enemies cost no tokens.
4. **Communication = optional `party_message` on the decision** (first §32 slice). The
   structured schema gains an optional `party_message` string. `AgentTurnService` stores
   accepted messages in a `PartyMessageBoard`; every agent's next prompt includes recent
   chatter. Broadcast-only, party-wide; whispers/targeted messages deferred. No new
   channel machinery (no tool executor) for a field the model already fills in the same
   call. Silence is a first-class choice: omitting the field or sending an empty string
   posts nothing.
5. **Party statlines and the encounter are configuration (§48).** `config/agents.toml`
   gains a required `[stats]` block per agent (ability scores, AC, HP, speed, weapon);
   a new `config/encounter.toml` defines the enemies. The CLI wires whatever the configs
   declare — party size and encounter size become data, honoring §17. Arin's statline
   stays in code (he is the human's character, not an agent).
6. **The board is agent-layer, not game truth (§10).** `PartyMessageBoard` lives in
   `src/application/agents/`, in-memory, no domain events, no persistence. Messages are
   agent chatter — the authoritative record of the combat remains the domain events.
7. **Information asymmetry is preserved structurally (§20).** Agents still see opponents
   as name + defeated status only; they cannot leak enemy HP into party chat because they
   never receive it. Message text is single-line (newlines collapsed) and truncated to
   200 characters — a cosmetic field must never burn a retry cycle.
8. **Fallback semantics unchanged, per-agent.** Each agent's turn independently gets the
   Plan 4 treatment: bounded transport retries, bounded decision attempts with rejection
   feedback, deterministic `first_living_opponent` fallback. One flaky agent never blocks
   the others. Fallback turns post no messages (the agent said nothing usable).
9. **Offline by default, unchanged.** `--agent off|llm|fake` semantics identical to
   Plan 4; `fake` mode scales to the whole party with the same scripted decision closure.

## 3. Components

### 3.1 `src/application/agents/party_board.py` — new

```python
@dataclass(frozen=True)
class PartyMessage:
    actor_name: str
    text: str
    round_number: int

class PartyMessageBoard:
    def post(self, message: PartyMessage) -> None
    def recent(self, limit: int = 8) -> tuple[PartyMessage, ...]
```

In-memory append list; `recent` returns the last `limit` messages in order. No
thread-safety (single-threaded turn loop). Unbounded appends are fine at combat scale;
the read side is where the prompt budget is enforced (§22).

### 3.2 `src/application/agents/profiles.py` — stats join the profile

```python
@dataclass(frozen=True)
class AgentStats:
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    speed_ft: int
    max_hp: int
    weapon: WeaponSpec            # from application.commands — same type, same layer

@dataclass(frozen=True)
class AgentProfile:            # gains: stats: AgentStats
    ...

def load_agent_profiles(path) -> AgentProfileCatalog   # now requires [agents.*.stats]
```

Loader validation follows the existing structure-only pattern: each `[agents.<name>]`
requires `character_name`, `character_class` (validated against `CharacterClass`),
`persona`, `objective`, `model_profile`, **and** a `[stats]` sub-table with all nine
fields (ints; weapon fields non-empty strings / positive ints). Malformed shapes raise
`AgentProfileError(ValueError)`. This extends the Plan 4 config format — the shipped
`config/agents.toml` and its tests are updated in the same plan.

```toml
[agent]
max_action_retries = 2

[agents.brix]
character_name = "Brix"
character_class = "fighter"
persona = "A cautious sellsword who prefers finishing fights quickly and safely."
objective = "Survive the skirmish and protect Arin; engage the nearest threat."
model_profile = "player"

[agents.brix.stats]           # same statline as Arin
strength = 16
dexterity = 13
constitution = 15
intelligence = 10
wisdom = 12
charisma = 9
armor_class = 16
speed_ft = 30
max_hp = 12

[agents.brix.stats.weapon]
weapon_id = "longsword"
name = "Longsword"
damage_die_count = 1
damage_die_size = 8

# [agents.mira] — rogue: Str 10 Dex 16 Con 12 Int 14 Wis 12 Cha 10, AC 15, HP 10,
#                  shortsword 1d6. Persona: opportunistic skirmisher; finishes wounded
#                  foes and picks her shots. Objective: cull the weakest enemy each round.
# [agents.sera] — cleric: Str 14 Dex 10 Con 14 Int 9 Wis 16 Cha 12, AC 16, HP 11,
#                  mace 1d6. Persona: protective; watches the party's backs and calls
#                  out the biggest threat. Objective: keep allies standing; engage
#                  whatever presses the party hardest.
```

### 3.3 `src/application/encounter.py` — new: encounter as configuration

```python
@dataclass(frozen=True)
class EnemySpec:
    name: str
    level: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    speed_ft: int
    max_hp: int
    weapon: WeaponSpec            # from application.commands

def load_encounter(path) -> tuple[AddCharacterCommand, ...]
```

`config/encounter.toml` uses a `[[enemies]]` array of tables; the loader maps each entry
to an `AddCharacterCommand(character_type="enemy", ...)`. Validation: required fields,
positive ints, non-empty names, and **distinct names** (duplicate → `EncounterError`,
a `ValueError` subclass). Shipped contents:

```toml
[[enemies]]   # Goblin Scout   — Str 8 Dex 14 Con 10 Int 10 Wis 8 Cha 8, AC 13, HP 7,  scimitar 1d6
[[enemies]]   # Goblin Skulker — same statline as Goblin Scout
[[enemies]]   # Orc Brute      — Str 16 Dex 12 Con 14 Int 7 Wis 10 Cha 8, AC 15, HP 15, greataxe 1d12
```

### 3.4 `src/application/agents/character_agent.py` — the say field

```python
ATTACK_DECISION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["attack"]},
        "target_id": {"type": "string"},
        "public_message": {"type": "string"},
        "party_message": {"type": "string"},     # optional — NOT in required
    },
    "required": ["action_type", "target_id", "public_message"],
    "additionalProperties": False,
}

@dataclass(frozen=True)
class AgentDecision:
    proposal: AttackProposal
    public_message: str
    party_message: str | None = None
```

Mapping rules for `party_message` (defensive, never a rejection): missing/empty/
whitespace-only → `None`; otherwise strip, collapse internal newlines to spaces, and
truncate to 200 characters. System prompt rules gain one line: the agent *may* include
`party_message` — one short sentence coordinating with allies — and may omit it to stay
silent. `build_user_prompt(perception, *, rejection=None, party_messages=())` renders a
"Party chatter:" section when messages exist, in chronological order (oldest first), as
`- {actor_name} (round {n}): {text}`, bounded by the service to the last 8.

### 3.5 `src/application/agents/agent_turn_service.py` — board in the loop

```python
class AgentTurnService:
    def __init__(self, game_service, runtime, catalog, agent_profiles, *,
                 max_action_retries: int | None = None,
                 board: PartyMessageBoard | None = None) -> None   # None → own board
    ...

@dataclass(frozen=True)
class AgentTurnReport:
    ...                                    # unchanged Plan 4 fields
    actor_name: str                                  # NEW — for display
    party_message: str | None = None                 # NEW — the accepted chatter, if any
```

`take_turn` changes are two injections into the unchanged Plan 4 flow:

1. **Read:** the user prompt is built with `board.recent(limit=8)` — every agent sees the
   party's recent chatter, including its own last words.
2. **Write:** only after an **accepted** model turn: if `decision.party_message` is not
   `None`, post `PartyMessage(actor_name, text, perception.round_number)`. Rejected
   attempts and fallback turns post nothing.

One service still serves all registered agents — the board is shared by construction.

### 3.6 `src/interfaces/cli/app.py` — wire the party

- `_wire_agent` → `_wire_party(service, game_id, mode, console) -> AgentTurnService`:
  loads `config/agents.toml`, adds each agent via `add_character` from its configured
  stats (replacing the hard-coded Brix fighter builder for agents; `_fighter("Arin")`
  stays for the human), registers each with the service. One announcement line:
  `Brix, Mira, Sera join the party (AI-controlled, mode: {mode})`.
- **The encounter loads in every mode, `off` included.** The fight is game content, not
  agent configuration: `main()` adds the enemies from `config/encounter.toml`
  unconditionally, and the Plan 1 hard-coded `_goblin()` builder is deleted. `--agent
  off` keeps exactly zero agent output and zero agent turns — what changes versus Plan 4
  is only the encounter itself (2 goblins + orc instead of 1 goblin), which is this
  plan's declared game content. The one Plan 1 CLI test scripting `attack goblin` targets
  `attack goblin scout` by full name.
- Rendering: the agent turn line shows the character's name (`Brix: "I strike."`), the
  chatter line prints as `Brix says: Focus the orc.` when present, telemetry and
  `render_report` unchanged. (Plan 4's `Agent:` prefix is replaced by names now that
  three agents share the output; the two Plan 4 CLI tests asserting `Agent:` are updated.)
- The main loop needs **no changes**: the agent branch already dispatches any registered
  actor; `--agent off|llm|fake` semantics are identical to Plan 4.

### 3.7 Data flow (per agent turn — Plan 4 pipeline plus the board)

```text
Observe → board.recent() into prompt → LLM → structured decision (attack + optional say)
  → map/validate → rules engine → events → if accepted: board.post(message)
```

## 4. Failure-mode table

| Failure | Where | Behavior |
|---|---|---|
| `party_message` wrong type | gateway schema | `ModelInvalidResponseError` → transport retry (existing path) |
| `party_message` empty/whitespace | decision mapping | silently becomes `None` (silence) — no retry |
| `party_message` > 200 chars or multi-line | decision mapping | truncated/collapsed — no retry |
| Missing/invalid `[stats]`, duplicate enemy names, unknown class | config load | `AgentProfileError` / `EncounterError` at wire time → CLI red text, exit 2 |
| Unknown `model_profile` reference | config load | existing `AgentProfileError` path |
| Transport / decision budget exhausted for one agent | service | unchanged per-agent fallback (`first_living_opponent`); other agents unaffected |
| Fallback turn | service | attack only, posts no message |
| Agent-configured enemy HP in chatter | impossible | perception never contains enemy HP (§20, pinned by tests) |

## 5. Testing

No real LLM in CI (§46); `asyncio.run` bridging; no new dependencies; no domain changes.
New/updated tests:

- `tests/application/agents/test_party_board.py` — post/recent ordering; limit bound;
  empty board → empty tuple.
- `tests/application/agents/test_agent_profiles.py` — updated for the `[stats]` block:
  valid multi-agent file loads three profiles; missing/partial stats rejected; bad
  weapon fields rejected.
- `tests/application/test_encounter.py` — TOML → commands; distinct-name validation;
  duplicate names rejected.
- `tests/application/agents/test_character_agent.py` — schema: `party_message` optional
  (absent passes, present passes, wrong type fails); mapping: empty→None, truncate 200,
  newline collapse; prompt: chatter section renders sender + round, omitted when empty.
- `tests/application/agents/test_agent_turn_service.py` — accepted turn posts the
  message; rejected turn and fallback post nothing; **A's post appears in B's next
  prompt** (the multi-agent behavior pin); one shared board across three registered
  agents; full 4-party × 3-enemy fight completes offline with scripted decisions.
- `tests/interfaces/test_cli.py` — `--agent fake` full fight with the three-agent party
  and three enemies reaches "ended"; all three enemy names resolve as targets; agent
  lines render by name with the chatter line; `--agent off` shows no agent activity;
  Plan 4 `Agent:` assertions updated to name-based rendering; the Plan 1 full-fight test
  updated to the configured encounter (`attack goblin scout` etc.).

## 6. Non-goals (deferred)

- Whispers / targeted messages, message persistence (Postgres `party_messages`), message
  reactions.
- `AgentScheduler` extraction — waits for the FastAPI consumer (Phase 11).
- New agent actions (dodge/help/spells) — waits on rules-engine support.
- GM agent, NPC conversation (Phase 7 scope).
- §19 human-instruction interpretation; autonomy policy refusals.
- Memory systems, vector retrieval (Phase 10).
- Any change to `src/domain/`, dice, combat math, or event types.

## 7. Global constraints

- Domain layer untouched; stdlib-only; no new runtime dependencies.
- Provider names and model ids only under `src/infrastructure/llm/` and as config values
  in `config/*.toml`.
- All model profiles remain `z-ai/glm-5.3-flash` (standing directive until final version).
  A full `--agent llm` fight is ~25–35 calls — a few cents on the cheap profile; `--agent
  fake` stays fully offline for demos and tests.
- Secrets from environment only; never committed or logged. No private chain-of-thought
  requested, displayed, or persisted (§33).
- mypy strict, ruff clean, pytest green offline at every task boundary; conventional
  commits scoped by layer with the Co-Authored-By trailer.

## 8. Completion checklist

- [ ] `src/domain/` has zero diff vs `master`; `src/ai/agents/` purity test still passes.
- [ ] Party size and encounter size are configuration; no agent statline or enemy statline
      in CLI code.
- [ ] Agent turns mutate state only through `submit_action`; messages post only after
      accepted model turns.
- [ ] Enemy HP/AC never enter any prompt or party message (pinned by tests).
- [ ] Every agent independently bounded: transport retries, decision attempts, fallback.
- [ ] Full suite green offline without `OPENROUTER_API_KEY` or `DATABASE_URL`.
- [ ] `--agent off`: zero agent output and zero agent turns; the encounter comes from
      `config/encounter.toml` in all modes (the fight is the same, only participation
      changes).
- [ ] No provider SDK outside infrastructure; no new dependencies.
