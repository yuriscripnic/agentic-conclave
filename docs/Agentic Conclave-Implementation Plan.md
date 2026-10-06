# Agentic Conclave Multi-Agent RPG — Implementation Plan

**Version:** 0.1  
**Status:** Active  
**Audience:** Claude Code, project contributors  
**Primary reference:** `CLAUDE.md`  
**Architecture reference:** `docs/architecture/domain-model-and-api.md`

---

## 1. Purpose

This document defines the implementation sequence for the Agentic Conclave Multi-Agent RPG.

The project must be implemented incrementally as a **modular monolith**.

The implementation must establish a deterministic and testable D&D game engine before introducing LLM-based agents.

The core architectural rule is:

> **LLMs propose. The domain decides. The game engine executes. Events record what happened.**

The implementation plan deliberately avoids premature distributed-system complexity.

---

# 2. Implementation Principles

## 2.1 Deterministic core first

The D&D rules engine must not depend on:

- an LLM
- OpenRouter
- a specific AI framework
- PostgreSQL
- FastAPI
- Rich
- network access

The rules engine must be executable and testable independently.

---

## 2.2 Test-first development

Use a test-driven workflow wherever practical:

1. Define expected behavior.
2. Write a failing test.
3. Implement the smallest solution.
4. Run focused tests.
5. Refactor.
6. Run the complete relevant test suite.

Do not implement large untested features.

---

## 2.3 Small vertical increments

Prefer small completed slices over large partially implemented subsystems.

Each phase should leave the repository in a runnable state.

---

## 2.4 No speculative infrastructure

Do not introduce:

- Kafka
- microservices
- Kubernetes
- Redis
- Celery
- distributed event buses
- complex agent frameworks

unless a later requirement actually justifies them.

The initial architecture is a modular monolith.

---

## 2.5 Domain independence

The dependency direction must remain:

```text
interfaces
    ↓
application
    ↓
domain

AI / infrastructure
    ↓
application / domain interfaces

domain
    ↓
nothing external
```

The domain must not import infrastructure or interface-layer code.

---

# Roadmap Structure

The phases below are grouped into three parts.

**Part I - Deterministic core.** Phases 0-7. Complete.

**Part II - Rules Core.** The R1-R10 programme plus the Bridge. This is the only
active work. Phase 2 in `CLAUDE.md` §52 is this programme; it is not complete
until R10 and the Bridge are done.

> **PART II GATE: No Part III work resumes, and no new agentic plan is written, until R10 and the Bridge are complete.**

**Part III - AI platform.** Phases 8-21. Built and tested, but **Frozen (pending Rules Core)**.

> **FROZEN ADAPTER LICENCE: Part III adapters may be updated only enough to keep the existing suite green; no new agent capability is added until the Bridge.**

---

# 3. Phase 0 — Repository Bootstrap

## Goal

Create a clean Python project that can be tested, linted, type-checked, and executed locally.

## Tasks

Create:

```text
pyproject.toml
README.md
CLAUDE.md
.env.example
.gitignore

src/
tests/
docs/
data/
scripts/
```

Configure:

- Python version
- pytest
- Ruff
- type checker
- formatting
- test discovery
- package structure

Recommended baseline:

```text
src/
├── domain/
├── application/
├── ai/
├── infrastructure/
└── interfaces/
```

## Acceptance criteria

- Project installs successfully.
- Tests execute.
- At least one test passes.
- Linting works.
- Type checking works.
- Application package can be imported.
- No unnecessary dependencies exist.

---

# 4. Phase 1 — Domain Primitives

## Goal

Implement the foundation of the deterministic game model.

### 4.1 Typed identifiers

Implement strongly typed IDs for important domain entities.

Examples:

```text
GameId
CampaignId
CharacterId
AgentId
LocationId
QuestId
EventId
```

Avoid passing arbitrary strings throughout the domain when a meaningful identifier type is appropriate.

---

## 4.2 Ability scores

Implement:

```text
Strength
Dexterity
Constitution
Intelligence
Wisdom
Charisma
```

with:

- validation
- ability modifier calculation
- immutable/value-object semantics where appropriate

Modifier formula:

```text
floor((score - 10) / 2)
```

---

## 4.3 Proficiency

Implement proficiency bonus calculation based on character level.

Keep this logic inside the rules/domain layer.

Do not encode it in prompts.

---

## 4.4 Character

Implement the initial `Character` model with:

```text
id
name
character_type
class
level
ability_scores
hp
max_hp
armor_class
speed
conditions
inventory
resources
```

Use domain validation for invalid state.

---

## Acceptance criteria

Unit tests cover:

- ability score validation
- ability modifiers
- proficiency bonus
- character creation
- invalid HP
- invalid level
- valid state transitions

---

# 5. Phase 2 — Deterministic Dice Engine

## Goal

Create a reproducible dice subsystem.

Implement:

```text
DiceRoller
DiceResult
```

Support:

```text
d4
d6
d8
d10
d12
d20
d100
```

and generic dice expressions where appropriate.

---

## 5.1 Seeded randomness

The dice engine must support deterministic execution using a seed.

Example:

```text
seed = 12345
```

Given the same seed and sequence of rolls, the results must be reproducible.

---

## 5.2 Advantage and disadvantage

Implement:

```text
normal
advantage
disadvantage
```

for d20-based checks.

---

## 5.3 Critical results

Represent natural:

```text
1
20
```

explicitly where relevant.

Do not mix critical-hit rules with generic dice mechanics.

---

## Acceptance criteria

Tests verify:

- dice ranges
- seeded reproducibility
- advantage
- disadvantage
- natural 1
- natural 20
- invalid dice
- invalid number of dice

---

# 6. Phase 3 — Checks and Saves

## Goal

Implement deterministic resolution of common D&D checks.

Support:

```text
Ability Check
Saving Throw
Attack Roll
```

The engine should calculate:

```text
d20
+ ability modifier
+ proficiency when applicable
+ other deterministic modifiers
```

and return structured results.

Example:

```text
CheckResult(
    roll=15,
    modifier=5,
    total=20,
    success=True
)
```

Do not return presentation-specific strings from the domain.

---

# 7. Phase 4 — Actions

## Goal

Introduce a unified action model.

Implement:

```text
ActionType
ActionProposal
ValidationResult
ActionResolution
```

Initial actions:

```text
Attack
Ability Check
Saving Throw
Dash
Dodge
Disengage
Help
Hide
Ready
Search
Use Item
Move
```

Not every action needs complete D&D rules immediately.

Start with the actions required for the first playable combat slice.

---

## Important rule

An AI or human may propose:

```text
Attack(target_id="goblin-1")
```

but the proposal must be validated by the domain.

The caller cannot directly modify:

```text
HP
inventory
resources
conditions
position
```

---

# 8. Phase 5 — Combat Engine

## Goal

Implement the first complete deterministic combat loop.

Implement:

```text
CombatState
TurnState
Initiative
Rounds
Turns
Attack resolution
Damage
Critical hits
Defeat
```

Initial combat flow:

```text
Start encounter
      ↓
Roll initiative
      ↓
Determine active character
      ↓
Receive action proposal
      ↓
Validate action
      ↓
Resolve action
      ↓
Apply state changes
      ↓
Emit events
      ↓
Advance turn
```

---

## First combat scenario

Implement a deterministic scenario:

```text
Party:
  Arin — Fighter

Enemy:
  Goblin
```

The Fighter must be able to attack the Goblin.

The encounter should terminate when the Goblin reaches 0 HP.

---

# 9. Phase 6 — Domain Events

## Goal

Represent important state changes as immutable events.

Initial events:

```text
GameCreated
GameStarted
CombatStarted
TurnStarted
AttackRequested
AttackResolved
DamageApplied
CharacterDefeated
TurnEnded
CombatEnded
```

Events should contain sufficient structured information for debugging and future replay.

Events must not depend on Rich, FastAPI, PostgreSQL, or an LLM.

---

## Event principle

Current state is authoritative for gameplay.

Events represent what happened.

Do not implement full event sourcing yet.

---

# 10. Phase 7 — First Playable CLI

## Goal

Expose the deterministic game through a Rich CLI.

Architecture:

```text
CLI
 ↓
Application Service
 ↓
Domain
 ↓
Events
 ↓
Presentation Model
 ↓
Rich Renderer
```

The domain must never import Rich.

---

## CLI requirements

Display:

- party
- enemies
- HP
- AC
- conditions
- current round
- active character
- available actions
- combat results

Example:

```text
Round 1 — Arin's turn

> attack goblin-1
```

---

# Part II — Rules Core (R1-R10)

The R1-R10 programme plus the Bridge. This is the only active work. Each R-plan
produces working, testable software on its own, ends in a runnable CLI milestone
with tests, and is written when its turn comes. Ordering and dependencies are
authoritative in `docs/superpowers/plans/README.md`.

## R1 — Grid & space

Battle map of 5-ft squares, coordinates, distance in feet (5e diagonal rule),
occupied squares, reach, cover (+2/+5 AC), and line-of-sight validation.

**Exit:** an attacker out of line of sight or behind cover resolves
deterministically; §28's "target 100 ft away" reproduces exactly.

## R2 — Ruleset & data

`Ruleset` port; `data/rules/*.toml` layout and validating loader; CC-BY-4.0
NOTICE; migrate existing weapon/class/monster constants.

**Exit:** rules data loads from TOML behind the port; swapping the ruleset id is
configuration-only.

## R3 — Actions

Resolvers and events for the nine inert actions; `BONUS_ACTION` and `REACTION`
gain real members (off-hand attack, opportunity attack).

**Exit:** every `ActionType` member has a resolver, events and a CLI path; no
dead enum values.

## R4 — Conditions

Typed SRD condition set with an effects table applied at the correct resolution
points; application, removal and recovery.

**Exit:** every condition alters rolls, movement or actions per SRD 5.2, tested
per condition.

## R5 — Life & death

0 HP to unconscious, death saving throws (3/3), damage-at-0, massive damage,
stabilization, healing, short and long rests.

**Exit:** the full down-and-recover cycle is deterministic and replayable.

## R6 — Skills & contests

Skill list, proficiency, passive scores, contested checks (grapple/shove).

**Exit:** `CheckResolver`'s check and save paths are reachable from real actions.

## R7 — Inventory

Item and armor models, equip/unequip, armor to AC, consumables, loot, gold,
carry capacity.

**Exit:** inventory is playable state, not persistence-only.

## R8 — Progression

XP thresholds, level-up, hit dice, ASI, class features for Fighter, Rogue,
Wizard and Cleric.

**Exit:** a character levels 1 to 20 deterministically.

## R9 — Spellcasting

Spell model, slots, known/prepared, cantrips, spell attacks and saves, grid AoE
templates, concentration, rituals. Phased: 9a slots and damage, 9b control and
concentration, 9c utility and rituals, 9d full four-class SRD list.

**Exit:** a Wizard and a Cleric play by SRD spell rules against the grid.

## R10 — Conformance

Seeded SRD conformance and property suite; rules-coverage report.

**Exit:** the suite is the gate; no LLM anywhere in it.

## Bridge

Update `ai/` perception, context and tools to the new interfaces, then unpause
Part III.

**Exit:** the agent suite is green against grid, conditions and spells.

---

# 11. Phase 8 — Persistence (Part III — Frozen (pending Rules Core))

## Goal

Persist campaign/game state using PostgreSQL.

Introduce infrastructure implementations for repository interfaces.

Persist at minimum:

```text
Campaign
Game
Character
World state
Events
```

The domain must remain database-independent.

---

## Transactions

Commands that modify game state must execute atomically.

Example:

```text
validate action
→ resolve action
→ update state
→ persist event
→ commit
```

If the transaction fails, the game state must not be partially updated.

---

# 12. Phase 9 — Model Gateway (Part III — Frozen (pending Rules Core))

Only after the deterministic core is stable should the LLM layer be introduced.

Implement:

```text
ModelGateway
ModelRequest
ModelResponse
StructuredModelResponse
LLMInvocation
```

Required capabilities:

```text
generate()
generate_structured()
stream()
embed()
```

Not every provider needs every capability initially.

---

## Provider architecture

Application code must depend on:

```text
ModelGateway
```

rather than:

```text
OpenRouter SDK
Z.ai SDK
OpenAI SDK
Anthropic SDK
```

Provider-specific code belongs under:

```text
infrastructure/llm/
```

---

# 13. Phase 10 — Fake Model Gateway (Part III — Frozen (pending Rules Core))

Before relying on a real LLM, implement:

```text
FakeModelGateway
```

It should return deterministic structured responses.

This enables tests such as:

```text
LLM proposes Attack
        ↓
Validator accepts Attack
        ↓
Rules Engine resolves Attack
```

without network access.

---

# 14. Phase 11 — First Character Agent (Part III — Frozen (pending Rules Core))

Implement one AI character agent.

Recommended first character:

```text
Fighter
```

The agent contains:

```text
Identity
Personality
Goals
State
Memory
Policies
Capabilities
Context Builder
Model
```

Initial decision loop:

```text
Observe
 ↓
Build context
 ↓
Ask model
 ↓
Parse structured response
 ↓
Validate action
 ↓
Execute valid action
```

---

## Critical constraint

The model does not execute game actions directly.

The model produces:

```text
ActionProposal
```

The application/domain decides whether it is legal.

---

# 15. Phase 12 — Retry and Recovery (Part III — Frozen (pending Rules Core))

Handle:

- malformed model output
- invalid actions
- unavailable tools
- provider errors
- timeouts
- rate limits

Retries must be bounded.

Never create an infinite agent retry loop.

Record:

```text
retry_count
failure_reason
request_id
agent_id
game_id
```

---

# 16. Phase 13 — GM Agent (Part III — Frozen (pending Rules Core))

Implement the Game Master agent.

Responsibilities:

- narration
- NPC interaction
- encounter initiation
- quest progression
- world consequences
- story orchestration

The GM does not directly mutate authoritative game state.

The GM proposes changes/actions that must pass through application/domain logic.

---

# 17. Phase 14 — Multi-Agent Party (Part III — Frozen (pending Rules Core))

Add additional character agents.

Initial party:

```text
Fighter
Rogue
Wizard
Cleric
```

Party size must remain configurable.

Do not hardcode exactly four agents.

---

## Communication

Implement controlled party communication.

Separate:

```text
private agent context
```

from:

```text
public party communication
```

Agents must not automatically receive another agent's private memory/context.

---

# 18. Phase 15 — Memory (Part III — Frozen (pending Rules Core))

Implement:

```text
Working Memory
Episodic Memory
Semantic Memory
```

Start with the simplest useful implementation.

Then introduce PostgreSQL + pgvector for semantic retrieval.

Memory retrieval must be relevant and bounded.

Never dump the entire game history into an LLM context.

---

# 19. Phase 16 — Context Engineering (Part III — Frozen (pending Rules Core))

Create a dedicated context builder.

Context should be assembled from:

```text
system instructions
identity
personality
current situation
relevant game state
goals
relevant memories
available actions
recent public conversation
```

Do not blindly serialize the entire database/game state.

---

# 20. Phase 17 — Observability (Part III — Frozen (pending Rules Core))

Add structured telemetry.

Implement:

```text
LLMInvocation
```

with:

```text
request_id
game_id
agent_id
model
provider
input_tokens
output_tokens
total_tokens
latency_ms
estimated_cost
tools_called
retrieval_count
retry_count
timestamp
status
error
```

Use OpenTelemetry when the core implementation is stable.

---

# 21. Phase 18 — Evaluation (Part III — Frozen (pending Rules Core))

Create repeatable evaluation scenarios.

Measure:

```text
rule violations
invalid actions
tool errors
latency
tokens/game
cost/game
decision quality
cooperation
memory usage
consistency
```

Use deterministic fixtures wherever possible.

Do not evaluate hidden chain-of-thought.

Evaluate observable behavior and outcomes.

---

# 22. Phase 19 — Web API (Part III — Frozen (pending Rules Core))

Introduce FastAPI after the CLI/game application layer is stable.

Initial API:

```text
/api/v1/campaigns
/api/v1/games
/api/v1/games/{game_id}
/api/v1/games/{game_id}/input
/api/v1/games/{game_id}/actions
/api/v1/games/{game_id}/status
/api/v1/games/{game_id}/events
```

API DTOs must not become domain models.

---

# 23. Phase 20 — Web UI (Part III — Frozen (pending Rules Core))

Build a Web UI after the backend contract is stable.

Potential technologies can be selected later.

The Web UI must consume the application/API layer rather than directly manipulating domain state.

---

# 24. Phase 21 — Advanced Features (Part III — Frozen (pending Rules Core))

Only after the core system is reliable consider:

- dynamic world generation
- procedural regions
- dynamic NPC generation
- faction simulation
- economy
- advanced spells
- more classes
- voice interaction
- Telegram
- model routing
- model comparison
- replay/debugging UI
- event sourcing
- distributed workers
- advanced agent coordination

These are deliberately postponed.

---

# 25. Definition of Done

A feature is not complete merely because the code exists.

A feature is complete when:

- behavior is implemented
- tests exist
- tests pass
- types are valid
- linting passes
- architecture boundaries are respected
- invalid inputs are handled
- public interfaces are documented where necessary
- no unrelated refactoring was introduced
- configuration is externalized where appropriate
- no secrets are committed

---

# 26. First Milestone

The first milestone is:

## MVP-0 — Deterministic Combat Sandbox

It must support:

```text
Create game
    ↓
Create Fighter
    ↓
Create Goblin
    ↓
Start combat
    ↓
Roll initiative
    ↓
Fighter attacks Goblin
    ↓
Validate action
    ↓
Resolve attack
    ↓
Roll damage
    ↓
Apply damage
    ↓
Emit events
    ↓
Display result
```

This milestone must work **without an LLM**.

---

# 27. First Implementation Task

The first Claude Code task is intentionally small.

Implement:

```text
Phase 0
+
Typed IDs
+
AbilityScores
+
ability modifiers
+
proficiency bonus
+
minimal Character model
```

Do not implement:

- LLM integration
- agents
- PostgreSQL
- FastAPI
- combat
- memory
- OpenRouter
- web UI

until the initial domain foundation has been reviewed and tests pass.

---

# 28. Architectural Guardrails

Before adding a dependency or abstraction, ask:

1. Does the domain actually require it?
2. Can this remain behind an interface?
3. Does it introduce infrastructure into the domain?
4. Is it required now or merely useful later?
5. Can the behavior be tested deterministically?

Prefer the simplest design that preserves the architecture.

---

# 29. Source-of-Truth Hierarchy

When documents disagree, use:

1. `CLAUDE.md` for development rules
2. `docs/architecture/domain-model-and-api.md` for contracts
3. `docs/implementation-plan.md` for implementation sequence
4. tests for executable behavioral expectations
5. source code as the current implementation

If an architectural conflict is discovered, stop and resolve it rather than silently inventing a third design.

---

# 30. Final Development Strategy

The project should evolve through increasingly complete vertical slices:

```text
Foundation
    ↓
Deterministic Rules
    ↓
Combat
    ↓
Events
    ↓
CLI
    ↓
Persistence
    ↓
Model Gateway
    ↓
One AI Agent
    ↓
GM
    ↓
Multi-Agent Party
    ↓
Memory
    ↓
Observability
    ↓
Evaluation
    ↓
API
    ↓
Web UI
    ↓
Advanced AI
```

The objective is not to build every feature quickly.

The objective is to demonstrate that a complex AI system can be built with:

- deterministic foundations
- explicit boundaries
- reliable state management
- structured AI outputs
- controlled autonomy
- persistent memory
- provider independence
- observable behavior
- measurable quality
- incremental engineering discipline