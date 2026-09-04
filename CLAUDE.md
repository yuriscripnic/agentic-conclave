# CLAUDE.md

## Agentic Conclave Multi-Agent RPG — Claude Code Project Instructions

This repository contains a production-oriented **AI-powered multi-agent D&D RPG**.

The project is simultaneously:

1. A playable AI-driven D&D game.
2. A portfolio-quality AI engineering project.
3. A reusable multi-agent AI platform.
4. A demonstration of clean architecture, deterministic domain logic, agent orchestration, memory, observability, evaluation, and model abstraction.

These instructions are mandatory for all implementation work.

---

# 1. Primary Architectural Principle

The most important rule in this repository is:

> **LLMs propose. The domain decides. The game engine executes. Events record what happened.**

Never allow an LLM to become the source of truth for game state or game rules.

The architecture must maintain this separation:

```text
Human / UI
    ↓
Application Layer
    ↓
AI Platform ───────────────┐
    ↓                      │
LLM                        │
    ↓                      │
Action Proposal             │
    ↓                      │
Rules Validation ←──────────┘
    ↓
Game Engine
    ↓
Domain Events
    ↓
Game State
    ↓
Persistence
```

---

# 2. Non-Negotiable Rules

## 2.1 Never put game rules in prompts

Do not rely on the LLM to determine:

- whether an attack is legal;
- whether a target is in range;
- whether a character has enough movement;
- whether a spell slot exists;
- how much damage an attack deals;
- whether a critical hit occurred;
- whether a character is dead;
- whether an action is available;
- whether an item exists;
- whether a character possesses an item;
- dice results;
- HP changes;
- inventory changes.

The LLM may reason about these things, but the deterministic rules engine MUST decide them.

---

## 2.2 Never allow direct LLM state mutation

Forbidden:

```python
character.hp -= damage
```

inside an LLM/tool adapter.

Forbidden:

```python
game.inventory["gold"] += 100
```

because an LLM requested it.

Forbidden:

```python
db.execute("UPDATE characters SET hp = ...")
```

from an agent.

Correct:

```text
LLM
 ↓
ActionProposal
 ↓
Application Service
 ↓
Rules Engine
 ↓
Domain Operation
 ↓
Domain Event
 ↓
Persistence
```

---

## 2.3 Never trust model-generated tool calls

Every tool call must be:

1. parsed;
2. schema validated;
3. permission checked;
4. game-state validated;
5. rules validated;
6. executed through an application/domain service.

A valid JSON response from an LLM is NOT automatically a valid game action.

---

# 3. Architecture

Use a **modular monolith** initially.

Do NOT introduce:

- microservices;
- Kafka;
- Kubernetes;
- service meshes;
- distributed queues;

unless a concrete requirement appears that cannot reasonably be solved inside the modular monolith.

The project should have clean internal boundaries so that components can later be extracted if necessary.

---

# 4. Layer Boundaries

The primary structure is:

```text
src/
├── domain/
├── application/
├── ai/
├── infrastructure/
└── interfaces/
```

Dependency direction:

```text
interfaces
    ↓
application
    ↓
domain

ai → application/domain abstractions

infrastructure → application/domain abstractions
```

The domain MUST NOT depend on:

- FastAPI;
- Rich;
- PostgreSQL;
- SQLAlchemy;
- OpenRouter;
- OpenAI;
- Anthropic;
- Ollama;
- LangChain;
- AutoGen;
- CrewAI;
- any other infrastructure framework.

---

# 5. Domain Layer

The domain contains authoritative game logic.

Expected areas:

```text
domain/
├── common/
├── rules/
│   ├── dice/
│   ├── abilities/
│   ├── actions/
│   ├── combat/
│   ├── conditions/
│   └── spells/
├── character/
├── world/
└── events/
```

The domain must be:

- deterministic where possible;
- testable without external services;
- independent of the LLM;
- independent of the database;
- independent of the UI.

---

# 6. Application Layer

The application layer coordinates use cases.

Examples:

```text
application/
├── campaigns/
├── games/
├── turns/
├── combat/
├── agents/
└── memory/
```

Application services may:

- load domain objects;
- execute commands;
- invoke domain services;
- invoke AI services;
- persist changes;
- publish events;
- construct DTOs/views.

Application services must not contain large amounts of game-rule logic.

If something is a rule of the game, put it in the domain/rules layer.

---

# 7. AI Layer

The AI platform is conceptually reusable beyond D&D.

```text
ai/
├── agents/
├── runtime/
├── context/
├── memory/
├── tools/
├── communication/
└── models/
```

Important abstractions:

```text
Agent
AgentRuntime
ContextBuilder
MemoryRepository
AgentTool
AgentToolExecutor
ModelGateway
AgentScheduler
AgentCommunicator
```

Do not couple these concepts to a specific AI framework.

---

# 8. Infrastructure Layer

Infrastructure contains implementations of interfaces.

Examples:

```text
infrastructure/
├── database/
├── llm/
├── vector/
├── events/
└── observability/
```

Provider-specific code belongs here.

For example:

```text
infrastructure/llm/openrouter/
infrastructure/llm/ollama/
infrastructure/llm/openai/
infrastructure/llm/anthropic/
```

The rest of the application should not know which provider is being used.

---

# 9. Interfaces Layer

Interfaces include:

```text
interfaces/
├── api/
└── cli/
```

Future:

```text
interfaces/
└── web/
```

Interfaces translate external input into application commands and application results into presentation models.

They must not implement game rules.

---

# 10. Domain Authority

The following are authoritative:

```text
Rules Engine
Game State
Domain Events
```

The following are NOT authoritative:

```text
LLM
Agent memory
Agent beliefs
Prompt
Narration
Conversation
UI
Database ORM models
```

The database persists authoritative state; it does not define game rules.

---

# 11. Game State vs History

Maintain both:

```text
Current Game State
+
Append-only Event History
```

Current state is optimized for gameplay.

Events are optimized for:

- history;
- debugging;
- auditing;
- replay;
- future event sourcing.

Do not prematurely implement complete event sourcing unless required.

---

# 12. Commands vs Events

Commands:

> Something wants to happen.

Events:

> Something happened.

Example:

```text
AttackCommand
    ↓
validation
    ↓
resolution
    ↓
AttackResolved
    ↓
DamageApplied
```

Never name an event as though it were a request.

Bad:

```text
AttackEvent
```

if it actually means "someone requested an attack."

Prefer:

```text
AttackRequested
AttackResolved
DamageApplied
```

---

# 13. D&D Rules

The initial ruleset is:

```text
dnd5e-srd-5.2
```

Use only legally permitted rules/content according to the project's licensing strategy, including applicable SRD 5.2 CC-BY-4.0 and/or ORC-licensed material.

Do not copy proprietary D&D book content into the repository unless it is legally permitted for this project.

The rules engine must be designed behind a ruleset abstraction.

Future rulesets should be possible.

---

# 14. Rules Implementation Order

Implement incrementally.

## Level 0

```text
d4
d6
d8
d10
d12
d20
d100
modifiers
advantage
disadvantage
seeded RNG
```

## Level 1

```text
ability scores
ability modifiers
proficiency
HP
AC
speed
level
class
```

## Level 2

```text
action
bonus action
reaction
movement

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
```

## Level 3

```text
initiative
rounds
turns
attacks
damage
death
conditions
```

## Level 4

Initially support a limited set of classes:

```text
Fighter
Rogue
Wizard
Cleric
```

Do not implement every class/subclass immediately.

## Level 5

Add data-driven spells.

---

# 15. Deterministic Dice

Dice must support seeded/reproducible execution.

Store:

```text
random seed
dice results
```

Never ask an LLM to generate dice results.

Bad:

```text
LLM:
"I rolled a 19."
```

Correct:

```text
Game Engine
    ↓
DiceRoller
    ↓
19
```

The LLM subsequently narrates the result.

---

# 16. Characters

A character and an agent are different concepts.

Character:

> What exists in the game?

Agent:

> What controls/operates that character?

Therefore:

```text
Character
    ↑
controlled by
    ↑
Agent
```

Do not combine them into one class.

---

# 17. Party Size

Party size is dynamic.

Never assume:

```python
party = [fighter, rogue, wizard, cleric]
```

The architecture must support configurable party sizes.

The initial game may use four or more AI characters, but the underlying architecture must support:

```text
1+
```

characters subject to configuration.

---

# 18. AI Character Model

Character agents should support:

```text
identity
personality
goals
fears
preferences
relationships
knowledge
memory
current objective
autonomy policy
capabilities
model profile
```

Personality influences decisions.

Personality does NOT override game rules.

---

# 19. Human Instructions

Human instructions are not necessarily direct commands to the game engine.

Example:

```text
"Go investigate the eastern tower."
```

This should generally become:

```text
human intent
    ↓
character interpretation
    ↓
agent decision
    ↓
action proposal
    ↓
validation
    ↓
execution
```

An autonomous character may reinterpret or refuse an instruction according to its configured autonomy policy.

However, all resulting actions must still pass deterministic validation.

---

# 20. Information Asymmetry

Agents must NOT automatically know the complete world state.

Maintain the distinction:

```text
World Truth
Agent Knowledge
Agent Belief
Agent Memory
```

Example:

```text
World:
There is an assassin behind the curtain.

Rogue:
Saw the assassin.

Fighter:
Heard the rogue mention movement.

Wizard:
Knows nothing.
```

Do not inject hidden world information into an agent's context.

---

# 21. Memory

Initial memory types:

```text
WORKING
EPISODIC
SEMANTIC
```

Working memory:

```text
current scene
current conversation
current objective
```

Episodic memory:

```text
things that happened to the character
```

Semantic memory:

```text
facts/beliefs/knowledge
```

Memory must be agent-specific.

Do not create one universal memory containing all knowledge.

---

# 22. Context Engineering

Never send the complete game state and complete history to every LLM call.

Build context from relevant information.

Recommended structure:

```text
System Instructions
Character Identity
Personality
Current Situation
Relevant World State
Relevant Party State
Retrieved Memories
Current Goals
Available Actions
Recent Conversation
```

Context construction must be a dedicated concern.

Do not build giant prompts directly inside API routes.

---

# 23. Model Gateway

All model calls go through:

```python
ModelGateway
```

Conceptual interface:

```python
async def generate(...)
async def generate_structured(...)
async def stream(...)
async def embed(...)
```

Agents reference model profiles:

```text
gm
player
cheap
reasoning
creative
embedding
```

not provider-specific model names.

---

# 24. Provider Abstraction

Initial provider:

```text
OpenRouter
```

Initial model configuration:

```text
Z.ai GLM
```

The implementation must make it possible to switch to:

```text
Ollama
OpenAI
Anthropic
other providers
```

without modifying agent logic.

Never write:

```python
from openai import OpenAI
```

inside an agent.

Provider-specific SDK usage belongs under infrastructure.

---

# 25. Structured LLM Output

Whenever an LLM is expected to make a machine-actionable decision, prefer structured output.

Example conceptual schema:

```json
{
  "action_type": "attack",
  "parameters": {
    "target_id": "goblin-1",
    "weapon_id": "longsword"
  },
  "public_message": "I will strike the goblin."
}
```

Validate the schema before processing it.

---

# 26. Action Proposal

An LLM produces:

```text
ActionProposal
```

not:

```text
GameState
```

The proposal must contain only the intended action.

Example:

```text
Attack
target = goblin-1
weapon = longsword
```

The engine determines:

```text
attack roll
hit/miss
critical
damage
conditions
resource consumption
death
XP
```

---

# 27. Agent Decision Pipeline

Standard pipeline:

```text
Agent Activated
    ↓
Observe
    ↓
Retrieve Memory
    ↓
Build Context
    ↓
LLM Inference
    ↓
Structured Output
    ↓
Action Proposal
    ↓
Validate
    ↓
Valid?
 ┌──┴─────┐
No       Yes
│          │
Retry      Game Engine
│          │
└──→       Events
           ↓
       Memory Update
```

The pipeline must be observable.

---

# 28. Invalid AI Actions

Invalid actions must not mutate state.

Example:

```text
Agent proposes attack
        ↓
Target 100 ft away
        ↓
Weapon range insufficient
        ↓
ActionRejected
        ↓
Retry
```

No HP changes occur.

Retry count must be configurable.

Example:

```yaml
agents:
  max_action_retries: 2
```

After retries are exhausted, use a deterministic fallback policy.

---

# 29. Tools

Tools must be explicit objects with:

```text
name
description
input schema
permission
handler
```

Tools should be narrow.

Prefer:

```text
attack
move
search
hide
talk
use_item
cast_spell
inspect
send_party_message
```

over a generic:

```text
modify_game_state
```

Never create an unrestricted game-state tool.

---

# 30. Tool Permissions

Initial permissions:

```text
READ_ONLY
GAME_ACTION
COMMUNICATION
```

Agents must only receive tools appropriate to their role.

The server/application layer must enforce permissions.

Never rely on the LLM to obey tool restrictions.

---

# 31. GM Agent

The GM can:

- narrate;
- manage NPC conversations;
- orchestrate encounters;
- progress quests;
- describe environments;
- introduce consequences;
- advance the story.

The GM cannot bypass the rules engine.

The GM should use tools to interact with the world.

---

# 32. Agent Communication

Agents have:

```text
private context
+
public party communication
```

Private context is not automatically shared.

Public messages are visible to appropriate party members.

Future support may include:

```text
negotiation
planning
disagreement
voting
persuasion
relationships
```

Do not expose private chain-of-thought as a substitute for communication.

---

# 33. Chain-of-Thought Policy

Never expose or persist private chain-of-thought.

Do not implement:

```text
agent.full_reasoning
```

or display raw hidden reasoning in the CLI.

If a user-facing explanation is useful, request a short explicit rationale:

```text
"I chose this because the enemy is within range and is the greatest immediate threat."
```

This is normal model output, not hidden reasoning.

---

# 34. Observability

Debug mode should expose useful telemetry.

At minimum:

```text
agent
provider
model
input tokens
output tokens
total tokens
latency
tool calls
memory retrieval count
retry count
estimated cost
status
```

Use a unified:

```text
LLMInvocation
```

representation.

Do not expose:

```text
API keys
private prompts
private memories
hidden chain-of-thought
credentials
internal security information
```

---

# 35. Correlation IDs

Important operations should have:

```text
request_id
correlation_id
causation_id
```

This should allow tracing:

```text
Human Input
    ↓
Agent Activation
    ↓
LLM Request
    ↓
Tool Call
    ↓
Action
    ↓
Dice
    ↓
Damage
    ↓
Event
    ↓
Narration
```

---

# 36. Persistence

Initial database:

```text
PostgreSQL
```

Vector memory:

```text
pgvector
```

Repository interfaces must hide database details from the domain.

Initial tables should conceptually include:

```text
campaigns
games
characters
party_members
locations
npcs
encounters
quests
quest_objectives
inventory_items
character_inventory
agents
agent_goals
agent_memories
party_messages
game_events
llm_invocations
```

---

# 37. Transactions

State-changing operations should use transaction boundaries.

Conceptually:

```text
BEGIN
    load state
    validate command
    resolve action
    update state
    append events
    persist
COMMIT
```

On failure:

```text
ROLLBACK
```

Avoid partial state mutations.

---

# 38. Concurrency

A game must not allow conflicting simultaneous state mutations.

Initial implementation may use:

```text
one logical command queue per game
```

or optimistic locking:

```text
game.version
```

Example:

```text
load version 42
    ↓
modify
    ↓
save WHERE version = 42
    ↓
version 43
```

If the version changed, reject with a concurrency error.

---

# 39. Idempotency

State-changing API operations should support:

```text
Idempotency-Key
```

Especially:

```text
POST /games
POST /input
POST /actions
```

A repeated request with the same idempotency key must not execute the action twice.

---

# 40. API Rules

FastAPI is an adapter.

API routes should:

1. validate HTTP input;
2. construct a command/query;
3. invoke an application service;
4. map the result to a response DTO.

API routes must NOT:

- roll dice;
- calculate damage;
- modify HP;
- access ORM entities directly for game mutations;
- invoke provider SDKs;
- contain D&D rules.

---

# 41. DTO Rules

Keep separate:

```text
HTTP DTO
Application Command
Domain Model
Persistence Model
```

Do not expose domain objects directly through FastAPI.

Example:

```text
HTTP Request
    ↓
ExecuteActionRequest
    ↓
ExecuteActionCommand
    ↓
Domain
    ↓
ActionResolution
    ↓
GameView
    ↓
HTTP Response
```

---

# 42. CLI Rules

Rich CLI is an adapter.

Architecture:

```text
Rich CLI
    ↓
Application Services
    ↓
Domain
```

The domain must never import Rich.

Do not print directly from domain services.

---

# 43. Game Status

The UI should expose useful game state.

At minimum:

```text
campaign
location
day/time
weather

party members
class
level
HP
AC
conditions
resources

combat round
current actor
initiative
enemies

quests

inventory
gold
spell slots
class resources

agent activity
```

---

# 44. Testing Philosophy

Tests are a first-class part of the architecture.

Prioritize deterministic domain tests.

Required tests include:

```text
dice
modifiers
proficiency
advantage
disadvantage
attack
critical hit
damage
AC
saving throws
conditions
movement
action economy
death
healing
inventory
spell resources
combat
turn order
```

---

# 45. AI Testing

Do NOT test hidden chain-of-thought.

Test observable behavior:

```text
agent produces legal actions
agent cannot attack nonexistent targets
agent cannot use nonexistent items
agent respects HP
agent respects resources
agent respects action economy
agent respects movement
agent uses relevant memories
agent does not know hidden information
agent reacts to human instructions
agent can refuse according to autonomy policy
agent communicates with party
agent retries invalid actions
```

---

# 46. Fake Model Gateway

CI tests must not require a real LLM.

Implement:

```text
FakeModelGateway
```

It should allow deterministic model responses.

Use it for:

```text
agent tests
integration tests
orchestrator tests
tool tests
API tests
```

Real provider calls belong in optional integration/evaluation tests.

---

# 47. Reproducibility

Record:

```text
random seed
domain events
LLM provider
LLM model
LLM request metadata
structured model output
configuration version
```

Remember:

> The game engine should be deterministic even when the LLM is not.

Do not pretend that LLM calls are deterministic.

---

# 48. Configuration

Use configuration rather than hardcoded values.

Important configuration:

```text
ruleset
party size
campaign
world
agent personalities
agent goals
model profiles
retry limits
database
LLM provider
debug mode
logging
```

Secrets must come from environment variables or an appropriate secret store.

Never commit credentials.

---

# 49. Error Handling

Use explicit domain/application errors.

Examples:

```text
GameNotFound
CharacterNotFound
InvalidAction
ActionNotAllowed
InvalidTarget
TargetOutOfRange
InsufficientResource
NotYourTurn
GameNotRunning
CombatNotActive
AgentDecisionFailed
ModelError
ModelTimeout
ToolError
PersistenceError
ConcurrentGameModification
```

Do not use generic exceptions to represent expected domain failures.

---

# 50. Logging

Use structured logging.

Important fields:

```text
timestamp
level
request_id
correlation_id
game_id
agent_id
character_id
operation
duration
status
error
```

Never log:

```text
API keys
credentials
private chain-of-thought
sensitive user data
```

---

# 51. Performance

Do not prematurely optimize.

Priority:

```text
1. Game correctness
2. Rules correctness
3. Agent reliability
4. Architecture
5. Observability
6. Performance
7. Cost
8. UI polish
```

Potential future optimizations include:

```text
context caching
memory retrieval optimization
parallel agent work
model routing
database indexing
response caching
```

Implement them only when justified.

---

# 52. Development Order

Implement in this order unless there is a strong reason not to.

### Phase 1

Deterministic domain:

```text
IDs
value objects
characters
abilities
inventory
world
game state
```

### Phase 2

Rules engine:

```text
dice
actions
combat
turns
conditions
damage
death
```

### Phase 3

Events:

```text
DomainEvent
EventEnvelope
EventRepository
```

### Phase 4

Application:

```text
GameService
TurnService
CombatService
QueryService
```

### Phase 5

Rich CLI.

### Phase 6

Model Gateway.

### Phase 7

GM Agent.

### Phase 8

Character Agent.

### Phase 9

Multi-agent party.

### Phase 10

Memory + pgvector.

### Phase 11

FastAPI.

### Phase 12

Web UI.

### Phase 13

Observability/evaluation improvements.

---

# 53. Definition of Done

A feature is not complete merely because the code works in one happy-path scenario.

Before considering a feature complete, verify:

- [ ] Architectural boundary is respected.
- [ ] Domain rules are deterministic where applicable.
- [ ] Invalid state transitions are rejected.
- [ ] Tests exist.
- [ ] Error handling exists.
- [ ] No provider-specific dependency leaked into domain/application code.
- [ ] No UI dependency leaked into domain.
- [ ] Events are generated when appropriate.
- [ ] Persistence behavior is correct.
- [ ] Logging/telemetry is appropriate.
- [ ] Existing tests still pass.
- [ ] No unnecessary infrastructure was introduced.

---

# 54. When Modifying Existing Code

Before changing architecture:

1. Inspect the existing module.
2. Identify its architectural layer.
3. Identify dependencies.
4. Check existing tests.
5. Preserve public contracts unless intentionally changing them.
6. Make the smallest safe change.
7. Add/update tests.
8. Run relevant tests.
9. Run the full test suite before declaring completion.

Do not rewrite large portions of the project simply because a different structure seems cleaner.

---

# 55. Dependency Management

Prefer small, well-understood dependencies.

Do not add a library simply because it makes a small task easier.

Before adding a dependency ask:

```text
Can this reasonably be implemented with the standard library?
Does this dependency belong in the current architectural layer?
Does it create provider/framework coupling?
Does it materially reduce complexity?
Is it maintained?
```

---

# 56. AI Framework Policy

AI frameworks are optional implementation details.

Do not make the architecture depend on:

```text
LangChain
LangGraph
AutoGen
CrewAI
Semantic Kernel
```

unless there is a demonstrated requirement.

The project's own abstractions must remain authoritative.

If an AI framework is introduced later, it belongs behind the AI/platform boundary.

---

# 57. No Framework-Driven Architecture

Do not design the application around a framework's preferred abstractions.

Design around:

```text
domain
use cases
contracts
events
agents
models
tools
```

Then adapt frameworks to those abstractions.

---

# 58. Documentation

Important architectural decisions should be documented.

When introducing a non-obvious architectural choice, add a concise explanation to the appropriate documentation.

For significant decisions, use an ADR:

```text
docs/adr/
```

Example:

```text
001-modular-monolith.md
002-model-gateway.md
003-event-history.md
004-agent-memory.md
```

---

# 59. Git Discipline

Do not create giant unrelated commits.

Prefer focused changes such as:

```text
feat(domain): add deterministic dice engine
feat(rules): implement attack resolution
feat(ai): add model gateway
feat(agent): implement character decision loop
test(rules): add combat validation tests
fix(agent): reject invalid target actions
```

Do not mix:

```text
architecture rewrite
new feature
formatting changes
dependency upgrade
```

in one unrelated change.

---

# 60. Code Quality

Prefer:

- explicit types;
- small functions;
- clear interfaces;
- dataclasses/value objects where appropriate;
- enums for closed sets;
- protocols for ports/interfaces;
- dependency injection;
- immutable objects where practical;
- meaningful names;
- deterministic tests.

Avoid:

- giant classes;
- giant functions;
- magic dictionaries;
- hidden global state;
- circular dependencies;
- excessive metaprogramming;
- unnecessary abstractions;
- framework magic.

---

# 61. Type Safety

Use Python typing consistently.

Prefer:

```python
def resolve_action(
    game: Game,
    action: ActionProposal,
) -> ActionResolution:
    ...
```

over:

```python
def resolve_action(game, action):
    ...
```

Use typed domain identifiers where appropriate.

---

# 62. State Mutation

Prefer explicit domain operations.

Bad:

```python
character.hp = character.hp - 10
```

from arbitrary application code.

Prefer:

```python
character.apply_damage(10)
```

or a domain service/action resolver.

State transitions should be easy to locate and test.

---

# 63. Rich CLI and Web UI Must Share Application Contracts

Do not implement separate game logic for:

```text
CLI
Web
API
```

They should all call the same application services.

Architecture:

```text
CLI ──────┐
Web ──────┼──→ Application
API ──────┘
```

---

# 64. Future Web UI

The future UI should be able to display:

```text
game map/location
party
combat
quests
inventory
agent activity
conversation
event history
LLM telemetry
```

Design application views so this is possible without rewriting domain logic.

---

# 65. Evaluation Framework

This is a flagship portfolio project.

Eventually implement evaluation scenarios measuring:

```text
rule adherence
legal action rate
invalid tool calls
agent consistency
memory relevance
information leakage
human instruction adherence
party cooperation
decision quality
latency
tokens/game
cost/game
```

Models should be comparable using the same scenarios.

Do not optimize purely for subjective "the game feels good."

---

# 66. AI Evaluation Principle

Separate:

```text
Game correctness
```

from:

```text
AI quality
```

Example:

```text
AI chooses Attack
    ↓
Rules Engine
    ↓
Correct result
```

A poor AI decision should not cause incorrect game mechanics.

---

# 67. Security

Agents must have least privilege.

Do not give agents unrestricted access to:

```text
filesystem
database
network
shell
process execution
```

Never execute model-generated Python or shell commands.

All external capabilities must be explicit tools.

---

# 68. Future Scaling

The architecture should be scalable internally, but do not prematurely distribute it.

Potential future decomposition:

```text
API Service
Game Service
Agent Runtime
Model Gateway
Memory Service
Event Service
Evaluation Service
```

Do NOT implement this decomposition now.

The initial system is a modular monolith.

---

# 69. Portfolio Quality

This project should demonstrate:

```text
clean architecture
domain-driven design
deterministic game engine
multi-agent orchestration
LLM abstraction
tool calling
context engineering
long-term memory
vector search
event-driven design
observability
evaluation
testing
configuration
reproducibility
```

Do not sacrifice architectural quality for a flashy demo.

A simple feature implemented correctly is more valuable than a sophisticated feature implemented with poor boundaries.

---

# 70. Final Rules

When uncertain, follow these principles:

### Correctness over cleverness.

### Domain rules over LLM output.

### Explicit contracts over framework magic.

### Deterministic state transitions over probabilistic behavior.

### Tests over assumptions.

### Small changes over rewrites.

### Interfaces over provider coupling.

### Application services over UI business logic.

### Events over invisible state changes.

### Relevant context over huge prompts.

### Least privilege over unrestricted agents.

### Observable behavior over hidden reasoning.

### Incremental architecture over premature infrastructure.

---

# 71. Final Mental Model

Always think about the system as:

```text
                 HUMAN
                   │
                   ▼
             INTERFACE
                   │
                   ▼
            APPLICATION
                   │
          ┌────────┴────────┐
          ▼                 ▼
        AI PLATFORM      GAME ENGINE
          │                 │
          ▼                 │
         LLM                │
          │                 │
          ▼                 │
    ACTION PROPOSAL         │
          │                 │
          └────────┬────────┘
                   ▼
              VALIDATION
                   │
              ┌────┴────┐
              │         │
           INVALID     VALID
              │         │
            RETRY       ▼
                    RESOLUTION
                        │
                        ▼
                      EVENTS
                        │
                ┌───────┴───────┐
                ▼               ▼
           GAME STATE         MEMORY
                │
                ▼
            PERSISTENCE
```

The fundamental invariant is:

```text
                LLM
                 │
                 │ proposes
                 ▼
          Action Proposal
                 │
                 ▼
        Deterministic Rules
                 │
                 ▼
           Game Engine
                 │
                 ▼
             Game State
```

**Never reverse this relationship.**

The LLM is the intelligence layer.

The rules engine is the authority.

The application layer is the coordinator.

The event system records what happened.

The memory system stores what agents remember.

The interfaces present the system.

The infrastructure is replaceable.

---

# 72. Source of Truth Hierarchy

When requirements appear to conflict, use this priority:

```text
1. Explicit user requirements
2. Domain correctness
3. This CLAUDE.md
4. Detailed architecture documentation
5. Existing public contracts
6. Existing implementation
7. Convenience
```

If an implementation conflicts with this document, do not silently violate the architecture.

Explain the conflict and propose an architectural change.

---

# 73. Completion Standard

Before reporting a task as complete, Claude Code should be able to answer:

```text
What changed?
Why was it changed?
Which architectural layer owns it?
Which tests verify it?
Can the feature work without a real LLM?
Can an invalid LLM action corrupt game state?
Did any provider-specific dependency leak across boundaries?
Were domain invariants preserved?
Were existing tests run?
```

If the answer to any of these is unclear, the task is probably not finished.