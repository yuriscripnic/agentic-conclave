# Agentic Conclave Multi-Agent RPG
## Architecture & Technical Design Document

**Document Status:** Architecture Baseline  
**Version:** 0.1  
**Purpose:** Source-of-truth architecture specification for implementation by AI coding agents such as Claude Code.

---

# 1. Project Overview

## 1.1 Objective

Build a production-oriented, AI-native D&D RPG system in which:

- A human player participates in a D&D campaign.
- Multiple autonomous AI-controlled characters form the player's party.
- An AI Game Master (GM) manages narration, encounters, NPC interaction, quests, and world progression.
- AI characters have personalities, goals, memories, relationships, and autonomous decision-making.
- The human player can issue commands to individual characters or the entire party.
- AI characters may agree, disagree, negotiate, or independently act according to their personalities and goals.
- A deterministic D&D rules engine is the authoritative source of game truth.
- LLMs provide reasoning, planning, communication, and narration but do not directly modify game state.
- The system supports dynamically configurable party sizes.
- The initial world is predefined.
- Future versions may support AI-generated/procedurally generated worlds and campaigns.
- The architecture is designed as a flagship AI engineering portfolio project.

The project should demonstrate both:

1. **Modern AI engineering**
2. **Senior-level backend/distributed-system architecture**

---

# 2. Core Architectural Principles

These principles are mandatory unless explicitly revised.

## 2.1 LLMs are not the source of truth

The LLM may:

- reason
- plan
- propose actions
- communicate
- narrate
- interpret information
- choose tools

The LLM must NOT directly:

- modify HP
- modify inventory
- create arbitrary game state
- determine dice results
- determine whether an action is legal
- arbitrarily modify character attributes
- bypass D&D rules

Example:

```text
LLM
  |
  | Proposed Action
  v
Game Engine
  |
  | Validate + Resolve
  v
Domain Events
  |
  v
Updated Game State
```

---

## 2.2 Deterministic Game Engine

The D&D rules engine must operate independently of the AI system.

The game engine must be usable without an LLM.

Example:

```python
result = combat_engine.attack(
    attacker=rogue,
    target=goblin,
    weapon=shortsword,
)
```

This operation must not require an LLM.

---

## 2.3 AI Platform must be reusable

The AI architecture should not be tightly coupled to D&D.

The conceptual AI platform should be reusable for other agent-based applications.

```text
AI Platform
    |
    +-- Agent Runtime
    +-- Model Gateway
    +-- Memory
    +-- Tool Calling
    +-- Context Engineering
    +-- Agent Communication
    +-- Evaluation
    +-- Observability
```

D&D is the first application/domain using this platform.

---

## 2.4 Provider independence

The application must not directly depend on a specific LLM vendor.

Initial provider:

```text
OpenRouter
```

Initial model:

```text
Z.ai GLM
```

Future providers:

```text
Ollama
OpenAI
Anthropic / Claude
Other OpenAI-compatible providers
Local models
```

The rest of the application must interact with an abstract model gateway.

---

## 2.5 Incremental implementation

Do not implement the complete architecture immediately.

The project must evolve through incremental milestones.

Avoid introducing infrastructure merely because it may be useful in the future.

Example:

Do not introduce Kafka in the first version unless a concrete requirement justifies it.

---

# 3. D&D Rules

## 3.1 Ruleset

The project will use:

- Wizards of the Coast 5e SRD 5.2 material released under CC-BY-4.0
- and/or ORC-licensed systems/content where appropriate

The repository must not copy non-permitted copyrighted D&D book content.

The architecture should be ruleset-oriented rather than hardcoding D&D concepts throughout unrelated infrastructure.

---

## 3.2 Ruleset abstraction

The architecture should conceptually support:

```text
Ruleset
   |
   +-- D&D 5e SRD 5.2
   |
   +-- Future Ruleset
```

The initial implementation only needs to support D&D 5e SRD 5.2.

Do not build multiple rulesets prematurely.

---

# 4. High-Level Architecture

```text
                         HUMAN PLAYER
                              |
                              v
                    +--------------------+
                    |      CLIENTS       |
                    |                    |
                    | Rich CLI           |
                    | Web UI             |
                    | Future Voice       |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    |   APPLICATION API  |
                    |                    |
                    | FastAPI             |
                    | Commands            |
                    | Queries             |
                    | Streaming           |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | GAME ORCHESTRATOR  |
                    |                    |
                    | Turn Manager       |
                    | Agent Scheduler    |
                    | Context Manager    |
                    | Command Router     |
                    | Event Coordinator  |
                    +----+-----------+---+
                         |           |
              +----------+           +----------+
              |                                 |
              v                                 v
    +--------------------+             +--------------------+
    |    AI PLATFORM     |             |    GAME ENGINE     |
    |                    |             |                    |
    | Agent Runtime      |             | D&D Rules          |
    | GM Agent           |             | Combat             |
    | Player Agents      |             | Characters         |
    | Memory             |             | Actions            |
    | Context            |             | Spells             |
    | Tool Calling       |             | Items              |
    | Model Gateway      |             | Conditions         |
    +---------+----------+             +---------+----------+
              |                                  |
              +----------------+-----------------+
                               |
                               v
                    +--------------------+
                    |    EVENT SYSTEM    |
                    |                    |
                    | Domain Events      |
                    | Game History       |
                    | Agent Events       |
                    | LLM Telemetry      |
                    +---------+----------+
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
        +-----------+   +-----------+   +--------------+
        |PostgreSQL |   | pgvector  |   |Observability|
        |           |   |           |   |             |
        |Game State |   | Memories  |   | Logs        |
        |Events     |   | Embeddings|   | Metrics     |
        |Campaigns  |   |           |   | Traces      |
        +-----------+   +-----------+   +--------------+

                              ^
                              |
                    +--------------------+
                    |    MODEL GATEWAY   |
                    |                    |
                    | OpenRouter / GLM    |
                    | Ollama              |
                    | OpenAI              |
                    | Claude              |
                    +--------------------+
```

---

# 5. Major Components

## 5.1 Client Layer

Initial clients:

1. Rich CLI
2. Web UI

Future:

3. Voice
4. Telegram
5. Other clients

Clients must not contain game rules.

Clients communicate with the application layer.

---

# 6. CLI

## 6.1 Requirements

The CLI must use:

- Python
- Rich
- interactive input

The CLI should provide a polished terminal experience rather than plain text output.

Example:

```text
╭──────────────────────────────────────────────╮
│              THE FORGOTTEN RUINS             │
╰──────────────────────────────────────────────╯

You stand before an ancient stone gate.

Party
───────────────────────────────────────────────
⚔ Aria       HP 31/31
🗡 Kael       HP 22/25
🧙 Eldrin     HP 18/18
✝ Mira        HP 27/27

> inspect the gate
```

---

## 6.2 CLI commands

System commands should be distinguishable from natural-language input.

Examples:

```text
/status
/party
/inventory
/quests
/save
/load
/debug
/help
/quit
```

Natural language:

```text
Let's inspect the eastern door.
```

---

## 6.3 CLI architecture

The game engine should not directly print Rich components.

Use:

```text
Game State / Events
        |
        v
Presentation Model
        |
        v
Rich Renderer
```

This allows Web UI and future clients to reuse the same application-level state.

---

# 7. Web UI

The Web UI is a later milestone.

It must expose useful game status information.

Potential layout:

```text
+------------------------------------------------------+
| Campaign / Location / Time / Weather                 |
+-------------------------------+----------------------+
|                               | PARTY                |
|          GAME VIEW            |                      |
|                               | Fighter  31/31 HP   |
|                               | Rogue    22/25 HP   |
|                               | Wizard   18/18 HP   |
|                               | Cleric   27/27 HP   |
|                               |                      |
+-------------------------------+----------------------+
| Input                                                 |
+------------------------------------------------------+
```

---

# 8. Game Status

Game status should be available independently from debug mode.

Status may include:

## Campaign

```text
Campaign
Location
Game day
Game time
Weather
```

## Party

```text
Character
Class
Level
HP
AC
Conditions
Resources
```

## Combat

```text
Combat state
Round
Current actor
Initiative order
Enemies
Conditions
```

## Quests

```text
Active quests
Completed quests
Quest objectives
```

## Resources

```text
Inventory
Gold
Spell slots
Class resources
```

---

# 9. Debug Mode

Debug mode must expose AI/LLM telemetry.

Debug information must NOT expose private chain-of-thought.

Instead expose observable metadata.

Example:

```text
╭────────────── AI DEBUG ──────────────────────╮
│ Agent: Kael                                  │
│ Model: GLM                                   │
│ Provider: OpenRouter                         │
│                                              │
│ Input tokens:       1,843                    │
│ Output tokens:        231                    │
│ Total tokens:       2,074                    │
│ Latency:           1.84s                     │
│                                              │
│ Tool calls: 2                                │
│ Memory retrieval: 5                          │
│ Retry count: 0                                │
╰──────────────────────────────────────────────╯
```

Possible telemetry:

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
tool_calls
retrieval_count
retry_count
status
error
timestamp
```

Optional context breakdown:

```text
system_tokens
character_tokens
world_tokens
memory_tokens
conversation_tokens
```

---

# 10. AI Agent Architecture

Agents are first-class components.

Conceptual model:

```text
Agent
 |
 +-- Identity
 +-- Personality
 +-- Goals
 +-- State
 +-- Memory
 +-- Policies
 +-- Capabilities
 +-- Context Builder
 +-- Model
```

Agent types:

```text
GM Agent
Character Agent
```

Character agents can represent:

```text
Fighter
Rogue
Wizard
Cleric
...
```

The number of character agents must be dynamically configurable.

---

# 11. Hybrid Agent Autonomy

AI characters are autonomous but can receive human instructions.

Example:

```text
Human:
"Rogue, check the door."
```

The Rogue normally follows the instruction.

However, agents can refuse or reinterpret unreasonable commands according to:

- personality
- goals
- fears
- current knowledge
- relationships
- game rules
- autonomy policy

Example:

```text
Human:
"Jump into the lava."

Rogue:
"No. I'm not doing that."
```

---

# 12. Character Agent State

Character agents should support:

```text
Identity
Personality
Goals
Fears
Preferences
Relationships
Knowledge
Memory
Current objective
Autonomy policy
```

Example:

```yaml
character:
  name: Aria
  class: Rogue

  personality:
    courage: 0.7
    greed: 0.8
    curiosity: 0.9

  goals:
    protect_party: 0.5
    obtain_treasure: 0.9
    avoid_death: 0.8

  autonomy:
    accept_human_orders: true
    override_threshold: 0.85
```

The exact representation can evolve.

---

# 13. GM Agent

The GM is responsible for:

- narration
- interpreting player actions
- managing encounters
- NPC interactions
- quests
- world progression
- presenting consequences
- orchestrating story progression

The GM should interact with the game through tools/services.

Potential capabilities:

```text
get_world_state
get_location
get_npc
create_npc
update_npc
create_quest
update_quest
describe_location
spawn_event
resolve_encounter
query_history
```

The GM must still obey the deterministic game engine.

---

# 14. Agent Tools

Tools are first-class objects.

Conceptually:

```text
Tool
 |
 +-- name
 +-- description
 +-- input_schema
 +-- permission
 +-- handler
```

Example:

```text
attack
```

Input:

```json
{
  "target_id": "goblin_03",
  "weapon_id": "shortsword"
}
```

The LLM sees the tool contract.

The tool handler invokes application/domain services.

---

# 15. Agent Decision Pipeline

Every autonomous agent decision should conceptually follow:

```text
Agent Activated
      |
      v
Observe Environment
      |
      v
Retrieve Relevant Memory
      |
      v
Build Context
      |
      v
LLM Inference
      |
      v
Proposed Action
      |
      v
Validate
      |
   +--+--+
   |     |
 valid invalid
   |     |
   v     v
Game   Reconsider /
Engine  Retry
   |
   v
Domain Events
   |
   v
Memory Update
```

---

# 16. Agent Communication

Use hybrid communication.

Agents have:

1. Private internal context
2. Public party communication

Private internal reasoning must not automatically be visible to other agents.

Public communication can be represented as messages.

Conceptual model:

```text
AgentMessage

sender
recipient
message_type
content
timestamp
conversation_id
priority
context
```

Example:

```json
{
  "sender": "rogue",
  "recipient": "party",
  "type": "proposal",
  "content": "We should investigate the eastern door first.",
  "confidence": 0.82
}
```

Future capabilities:

- negotiation
- disagreement
- persuasion
- voting
- party planning
- leadership

---

# 17. Human Input

Human input has different semantic categories.

Examples:

```text
System Command
Natural Language Intent
Direct Character Command
Question
Conversation
```

Architecture:

```text
Human Input
     |
     +---- /status ------> System Command
     |
     +---- "check door" -> Intent
                              |
                              v
                            Agent
                              |
                              v
                          Game Action
```

Avoid unnecessary LLM calls for simple system commands.

---

# 18. Game Engine

The Game Engine is deterministic and LLM-independent.

Responsibilities:

```text
Rules
Combat
Dice
Characters
Classes
Abilities
Actions
Spells
Items
Conditions
Resources
World state
```

The engine must validate all proposed actions.

---

# 19. Incremental Rules Engine

Implement in stages.

## Level 0 — Dice

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

Also:

```text
modifiers
advantage
disadvantage
```

Dice rolls should support deterministic testing via seeded RNG.

Example:

```text
seed = 12345
```

should allow reproducible simulations.

---

## Level 1 — Character Core

Implement:

```text
Ability scores
Ability modifiers
Proficiency
HP
AC
Speed
Level
Class
```

---

## Level 2 — Actions

Implement core action concepts:

```text
Action
Bonus Action
Reaction
Movement
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
```

---

## Level 3 — Combat

Implement:

```text
Initiative
Rounds
Turns
Attacks
Damage
Death
Conditions
```

---

## Level 4 — Classes

Initially implement a small number of classes.

Suggested initial classes:

```text
Fighter
Rogue
Wizard
Cleric
```

Do not implement every class/subclass immediately.

---

## Level 5 — Spells

Create a data-driven spell architecture.

Conceptual model:

```text
Spell
 |
 +-- level
 +-- school
 +-- casting_time
 +-- range
 +-- components
 +-- duration
 +-- target
 +-- effects
```

Spells should produce game-engine effects rather than allowing the LLM to directly modify state.

---

# 20. Rules/Data-Driven Design

Avoid hardcoding rules directly into agent prompts.

Prefer:

```text
Rules Data
    |
    v
Rules Engine
    |
    v
Game State
```

rather than:

```text
Prompt:
"The Wizard can cast..."
```

The agent should query authoritative game information through tools/context.

---

# 21. Game State vs Game History

Separate current state from historical events.

## Current state

```text
GameState
 |
 +-- Characters
 +-- Location
 +-- Enemies
 +-- Inventory
 +-- Quests
 +-- World state
```

## History

```text
EventStore
 |
 +-- Event 1
 +-- Event 2
 +-- Event 3
 +-- ...
```

Eventually:

```text
Current State = f(previous events)
```

Full event sourcing is a future capability, but the domain should be designed to support it.

---

# 22. Event System

Game events should be first-class.

Examples:

```text
AttackRequested
AttackResolved
DamageApplied
CharacterDefeated
ExperienceGranted
QuestProgressed
SpellCast
ItemObtained
CharacterMoved
ConversationOccurred
```

Conceptual flow:

```text
Command
   |
   v
Game Engine
   |
   v
Domain Event
   |
   +----> Game State
   +----> Memory
   +----> Analytics
   +----> UI
```

---

# 23. Event Storage

Potential event structure:

```text
game_events

id
game_id
sequence_number
timestamp
event_type
actor_id
payload
```

Example:

```json
{
  "event_type": "attack_resolved",
  "actor": "rogue_01",
  "target": "goblin_03",
  "attack_roll": 18,
  "damage": 7
}
```

Events should be immutable.

---

# 24. Memory Architecture

Memory is a separate subsystem.

Three conceptual layers:

```text
Memory
 |
 +-- Working Memory
 +-- Episodic Memory
 +-- Semantic Memory
```

---

## 24.1 Working Memory

Current context:

```text
Current scene
Current enemies
Current conversation
Current objective
Relevant party state
```

Likely represented in active agent context rather than long-term storage.

---

## 24.2 Episodic Memory

Historical events relevant to an agent.

Example:

```text
The fighter protected the wizard during the goblin attack.
The rogue discovered a secret door.
The merchant refused to pay the party.
```

---

## 24.3 Semantic Memory

Agent beliefs and knowledge.

Example:

```text
"The merchant is probably associated with the thieves guild."
```

Important:

Agent belief does not necessarily equal world truth.

---

# 25. World Truth vs Agent Belief

The architecture must support information asymmetry.

```text
                 WORLD STATE
                   Truth
                     |
          +----------+----------+
          |          |          |
          v          v          v
       Fighter     Rogue      Wizard
       beliefs     beliefs    beliefs
```

Agents should not automatically have access to all world state.

An agent can only know information that is:

- observed
- communicated
- remembered
- inferred
- legitimately retrieved

Future belief records may contain:

```text
fact
source
confidence
timestamp
validity
```

---

# 26. Context Engineering

Do not send the entire game state to the LLM on every request.

Construct context from relevant information.

Conceptual context:

```text
Agent Context
 |
 +-- System Instructions
 +-- Character Identity
 +-- Personality
 +-- Current Situation
 +-- Relevant World State
 +-- Relevant Party State
 +-- Retrieved Memories
 +-- Current Goals
 +-- Available Actions
 +-- Recent Conversation
```

Context construction must be its own component.

---

# 27. Model Gateway

The model gateway abstracts providers.

Conceptual interface:

```python
class ModelGateway:
    def generate(...)
    def generate_structured(...)
    def stream(...)
    def embed(...)
```

Provider implementations:

```text
OpenRouter
Ollama
OpenAI
Anthropic
Other providers
```

The rest of the application must depend on the abstraction rather than a provider-specific SDK.

---

# 28. Model Profiles

Models should be configurable.

Example:

```yaml
llm:
  default_provider: openrouter

  models:
    gm:
      provider: openrouter
      model: <configured-model>

    player:
      provider: openrouter
      model: <configured-model>

    cheap:
      provider: openrouter
      model: <configured-model>

    embedding:
      provider: openrouter
      model: <configured-model>
```

Agents should reference model profiles rather than hardcoded provider/model names.

Example:

```yaml
agents:
  fighter:
    model_profile: cheap

  wizard:
    model_profile: reasoning

  gm:
    model_profile: creative
```

---

# 29. Model Routing

Future capability:

```text
Task
 |
 v
Model Router
 |
 +-- Cheap Model
 +-- Reasoning Model
 +-- Creative Model
 +-- Local Model
```

Possible routing criteria:

```text
task type
latency
cost
quality
context size
availability
```

Do not implement sophisticated routing until multiple models are actually available.

---

# 30. Database

Initial persistence technology:

```text
PostgreSQL
```

Vector storage:

```text
pgvector
```

Potential entities:

```text
campaigns
games
players
characters
character_stats
character_abilities
items
spells
conditions
locations
npcs
quests

game_events

agent_profiles
agent_memories
agent_beliefs

conversations
messages

model_requests
model_responses
```

Future:

```text
evaluation_runs
evaluation_cases
agent_metrics
```

---

# 31. Party Architecture

Party size is dynamically configurable.

Do not hardcode party members.

Conceptually:

```text
Game
 |
 +-- Party
      |
      +-- Character
      +-- Character
      +-- Character
      +-- ...
```

Configuration example:

```yaml
party:
  human_players: 1
  ai_players: 4
```

Future:

```yaml
party:
  human_players: N
  ai_players: M
```

Version 1 supports one human but architecture should not prevent multiple humans later.

---

# 32. Agent Scheduling

Do not automatically invoke every AI agent every turn.

Use an Agent Scheduler.

Conceptually:

```text
Combat Round
     |
     v
Who needs to act?
     |
     +-- Human
     +-- Fighter AI
     +-- Rogue AI
     +-- Wizard AI
     +-- NPC
```

Only agents that need to make a decision should be activated.

This is important for:

- cost
- latency
- scalability
- deterministic turn management

---

# 33. Orchestrator

The Game Orchestrator coordinates the system.

Responsibilities:

```text
Turn management
Agent scheduling
Command routing
Context coordination
Game/AI interaction
Event coordination
Session lifecycle
```

It should not implement D&D rules.

It should coordinate domain services.

---

# 34. Application Layer

The application layer translates external requests into domain operations.

Potential conceptual services:

```text
GameService
CampaignService
TurnService
CombatService
CharacterService
AgentService
MemoryService
ConversationService
```

The exact service decomposition may change during implementation.

Avoid excessive microservices.

---

# 35. Initial Deployment Architecture

The first version should be a **modular monolith**.

Recommended:

```text
                    Application
                         |
       +-----------------+-----------------+
       |                 |                 |
   Game Engine       AI Platform       API/CLI
       |                 |                 |
       +-----------------+-----------------+
                         |
                    PostgreSQL
```

Do NOT start with microservices.

Do NOT start with Kubernetes.

Do NOT start with Kafka.

The internal module boundaries should be clean enough that components can be separated later if required.

---

# 36. Suggested Technology Direction

Initial technology candidates:

```text
Language:
Python 3.x

API:
FastAPI

CLI:
Rich

Database:
PostgreSQL

Vector:
pgvector

LLM:
OpenRouter

Initial model:
Z.ai GLM

Containers:
Docker

Testing:
pytest

Async:
asyncio

Configuration:
YAML/environment variables

Future observability:
OpenTelemetry
```

The exact versions should be selected during implementation based on current stable releases.

---

# 37. Repository Structure

Initial recommended structure:

```text
project-root/
│
├── src/
│   ├── domain/
│   │   ├── rules/
│   │   │   ├── dice/
│   │   │   ├── abilities/
│   │   │   ├── checks/
│   │   │   ├── combat/
│   │   │   ├── actions/
│   │   │   ├── conditions/
│   │   │   ├── spells/
│   │   │   └── progression/
│   │   │
│   │   ├── character/
│   │   ├── world/
│   │   └── events/
│   │
│   ├── application/
│   │   ├── game/
│   │   ├── turns/
│   │   ├── combat/
│   │   ├── agents/
│   │   ├── campaigns/
│   │   └── memory/
│   │
│   ├── ai/
│   │   ├── agents/
│   │   ├── runtime/
│   │   ├── memory/
│   │   ├── context/
│   │   ├── tools/
│   │   ├── models/
│   │   └── communication/
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── llm/
│   │   ├── vector/
│   │   ├── events/
│   │   └── observability/
│   │
│   └── interfaces/
│       ├── api/
│       ├── cli/
│       └── web/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── rules/
│   ├── agents/
│   └── evaluation/
│
├── data/
│   ├── rules/
│   ├── campaigns/
│   └── worlds/
│
├── config/
│
├── scripts/
│
├── docs/
│
├── docker/
│
├── pyproject.toml
├── README.md
└── .env.example
```

This structure is a starting point and should be refined as implementation begins.

---

# 38. Testing Strategy

The deterministic engine should have extensive unit tests.

Especially:

```text
Dice
Ability modifiers
Proficiency
Attack rolls
Damage
Critical hits
Conditions
Saving throws
Actions
Spells
Resources
Combat turns
Death
```

AI tests should focus on observable behavior.

Examples:

```text
Agent selects legal actions
Agent does not invent unavailable items
Agent respects current HP
Agent respects character capabilities
Agent retrieves relevant memories
Agent follows personality/goals
Agent can respond to human commands
```

Do not test hidden chain-of-thought.

---

# 39. Reproducibility

Games should support deterministic replay where practical.

The game should be able to record:

```text
random seed
game events
LLM requests
LLM responses/structured outputs
model information
configuration
```

This enables:

- debugging
- regression tests
- AI evaluation
- replay
- performance analysis

LLM calls may not be deterministic across providers/models, so deterministic game mechanics and recorded AI outputs should be treated separately.

---

# 40. Observability

Observability is a first-class concern.

Track:

```text
LLM latency
LLM tokens
LLM cost
Tool calls
Agent activation
Memory retrieval
Errors
Retries
Game events
Turn duration
```

Eventually use:

```text
OpenTelemetry
```

for distributed tracing/metrics.

---

# 41. AI Evaluation

A flagship AI project should include evaluation rather than relying solely on manual gameplay.

Potential evaluation dimensions:

## Rule adherence

Does the agent attempt illegal actions?

## Character consistency

Does the character behave according to personality/goals?

## Memory

Does the agent correctly recall relevant events?

## Knowledge boundaries

Does the agent know information the character should not know?

## Cooperation

Can multiple agents coordinate?

## Decision quality

Are selected actions reasonable?

## Performance

```text
tokens/game
latency/game
cost/game
```

---

# 42. Experiment Framework

Future capability:

```text
Experiment
 |
 +-- Model
 +-- Agent configuration
 +-- Prompt/context configuration
 +-- Game scenario
 +-- Evaluation metrics
```

Example:

```text
Experiment #17

Model A: GLM
Model B: Qwen
Model C: GPT

Games: 100

Metrics:
- Rule violations
- Tool errors
- Agent consistency
- Average latency
- Tokens/game
- Cost/game
- Decision quality
```

This is a major portfolio feature.

---

# 43. World Architecture

## Version 1

Use a simple predefined world.

Example:

```text
Campaign
 |
 +-- World
      |
      +-- Locations
      +-- NPCs
      +-- Encounters
      +-- Quests
      +-- Factions
```

Do not implement procedural generation initially.

---

## Future

Introduce:

```text
AI-generated NPCs
AI-generated quests
Procedural regions
AI-generated lore
Dynamic factions
World simulation
```

Eventually:

```text
World Simulation
      |
      +-- NPC activity
      +-- Faction activity
      +-- Time
      +-- Economy
      +-- Events
      +-- Quest progression
      |
      v
     GM
      |
      v
   Players
```

---

# 44. Future World Simulation

The GM should eventually not be the only entity responsible for world state.

Separate:

```text
World Simulation
        |
        +-- World State
        |
        +-- GM
```

The GM observes world events and narrates/orchestrates them.

This is a future architecture goal, not an MVP requirement.

---

# 45. Security and Safety Boundaries

Agents must operate through explicit capabilities.

An agent should not receive unrestricted access to:

```text
database
filesystem
network
application internals
```

Agents receive only explicitly permitted tools.

Tool permissions should be enforced by the application.

---

# 46. Configuration Philosophy

Avoid hardcoding:

- models
- API keys
- party size
- campaign
- world
- agent personalities
- model profiles

Configuration should be externalized where practical.

Secrets must be stored through environment variables or an appropriate secret mechanism.

Never commit API keys.

---

# 47. Development Phases

## Phase 1 — Deterministic Core

Implement:

```text
Dice
Character
Ability scores
Basic actions
Basic combat
Game state
Events
CLI
```

No autonomous AI required initially.

---

## Phase 2 — First AI GM

Implement:

```text
Model Gateway
GM Agent
Tool calling
Structured outputs
Natural language input
```

The GM operates against the deterministic engine.

---

## Phase 3 — First AI Character

Implement:

```text
Character Agent
Personality
Goals
Agent decision pipeline
Tool usage
Human commands
```

---

## Phase 4 — Multi-Agent Party

Implement:

```text
Dynamic party
Multiple character agents
Agent scheduler
Public party communication
Hybrid autonomy
```

---

## Phase 5 — Memory

Implement:

```text
Working memory
Episodic memory
Semantic memory
pgvector
Memory retrieval
Agent beliefs
```

---

## Phase 6 — Web UI

Implement:

```text
Game view
Party status
Combat status
Quest status
Inventory
Agent activity
```

Debug mode:

```text
tokens
latency
model
cost
tool calls
memory retrieval
```

---

## Phase 7 — Observability

Implement:

```text
structured logs
metrics
tracing
LLM telemetry
game telemetry
```

---

## Phase 8 — Evaluation

Implement:

```text
evaluation scenarios
rule adherence
memory tests
agent consistency
multi-agent cooperation
model comparison
```

---

## Phase 9 — Advanced AI

Potential:

```text
planning
negotiation
agent voting
advanced memory
model routing
context optimization
automatic evaluation
```

---

## Phase 10 — Advanced World

Potential:

```text
procedural world
AI-generated quests
NPC simulation
factions
dynamic economy
world events
```

---

# 48. Architecture Constraints for AI Coding Agents

An AI coding agent working on this repository MUST follow these principles.

## Do

- Preserve domain/application/infrastructure separation.
- Keep the game engine independent of LLM providers.
- Use structured outputs for agent actions.
- Validate every AI-proposed action.
- Keep game state authoritative in the deterministic engine.
- Write tests for domain logic.
- Make model providers configurable.
- Keep CLI/UI separate from domain logic.
- Add telemetry for LLM calls.
- Prefer incremental implementation.

## Do not

- Put D&D rules inside prompts.
- Allow an LLM to directly mutate database/game state.
- Hardcode a specific LLM provider throughout the code.
- Make every game component depend on an AI framework.
- Introduce Kafka/microservices/Kubernetes without a concrete requirement.
- expose private chain-of-thought in UI/debugging.
- hardcode the party size.
- hardcode specific characters into the core engine.
- mix Rich presentation code into domain logic.

---

# 49. Architectural Priority

When trade-offs occur, prioritize:

1. **Correctness of game state**
2. **Correctness of D&D rules**
3. **AI agent reliability**
4. **Clean architecture**
5. **Observability**
6. **Performance/cost**
7. **UI polish**

The LLM is an intelligent component inside the system, not the system itself.

---

# 50. Long-Term Vision

The final system should look conceptually like:

```text
                         PLAYER(S)
                            |
                            v
                     +-------------+
                     |   Clients   |
                     +------+------+
                            |
                            v
                     +-------------+
                     | Game API    |
                     +------+------+
                            |
                            v
                 +----------------------+
                 | Game Orchestrator   |
                 +----------+-----------+
                            |
             +--------------+--------------+
             |                             |
             v                             v
      +--------------+             +--------------+
      | AI Platform  |             | Game Engine  |
      |              |             |              |
      | GM           |             | Rules        |
      | Agents       |             | Combat       |
      | Memory       |             | Characters   |
      | Context      |             | World        |
      | Tools        |             | Spells       |
      | Models       |             | Items        |
      +------+-------+             +------+-------+
             |                            |
             +-------------+--------------+
                           |
                           v
                    +-------------+
                    | Event System|
                    +------+------+
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          State         Memory       Analytics
             |             |             |
             +-------------+-------------+
                           |
                           v
                    +-------------+
                    | PostgreSQL  |
                    | + pgvector  |
                    +-------------+
```

The project should evolve toward this architecture without attempting to implement every component in the first milestone.

---

# 51. Definition of Success

The project is successful when a developer can:

1. Start the application locally.
2. Create/load a campaign.
3. Enter a predefined D&D world.
4. Play through a Rich CLI.
5. Control their character using natural language.
6. Interact with autonomous AI party members.
7. Observe agents disagreeing/cooperating naturally.
8. Have the GM dynamically narrate events.
9. Have all actions validated by the deterministic rules engine.
10. Persist the campaign.
11. Inspect game status.
12. Enable debug mode and inspect LLM telemetry.
13. Replay/debug game events.
14. Change the LLM provider/model through configuration.
15. Run automated tests.
16. Run AI evaluation scenarios.
17. Eventually play through a Web UI.

The ultimate portfolio goal is to demonstrate:

> **The ability to design and implement a production-oriented multi-agent AI system with deterministic domain logic, persistent memory, model abstraction, observability, evaluation, and scalable architecture.**