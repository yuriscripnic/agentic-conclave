# Agentic Conclave — Implementation Plan Roadmap

This directory contains the executable implementation plans for the Agentic Conclave
Multi-Agent RPG. Plans are derived from, and must not contradict:

- `CLAUDE.md` — development rules (source-of-truth priority #3)
- `docs/Agentic Conclave-Implementation Plan.md` — phase sequence (source-of-truth priority #4-ish, per its §29)
- `docs/Agentic Conclave-architecture-overview.md` — architecture baseline

## Roadmap structure

> **PART II GATE: No Part III work resumes, and no new agentic plan is written, until R10 and the Bridge are complete.**

**Part I - Deterministic core.** Plans 1-2. Complete; unchanged.

**Part II - Rules Core (R1-R10) + Bridge.** The only active work. Rows 14-24.

**Part III - AI platform.** Plans 3-12. Frozen; green; not extended until Part II exits.

## Plan series

Each plan produces working, testable software on its own and follows the phase order
mandated by the Implementation Plan document.

> **Numbering note:** session shorthand for the 2026-09-06 work called the party
> plan "Plan 5" and the agent-memory plan "Plan 6". The canonical numbers are the
> table rows below (party = #6, memory = #7); the Status column is the authority
> on what has shipped.

| # | Plan file | Covers (Implementation Plan doc) | Status |
|---|-----------|----------------------------------|--------|
| 1 | `2026-09-03-deterministic-core-mvp0.md` | Phases 0-7 - domain primitives, dice, checks, actions, combat, events, first playable CLI (MVP-0) | Complete |
| 2 | `2026-09-04-persistence-postgres.md` | Phase 8 - PostgreSQL repositories, transactions, optimistic locking | Complete |
| 3 | `2026-09-04-model-gateway.md` | Phases 9-10 - ModelGateway + FakeModelGateway, model profiles, OpenRouter adapter | Frozen (pending Rules Core) |
| 4 | `2026-09-05-character-agent.md` | Phases 11-12 - character agent, decision pipeline, bounded retry, fallback | Frozen (pending Rules Core) |
| 5 | `2026-09-08-gm-agent.md` | Phase 13 - GM agent, narration, NPC talk | Frozen (pending Rules Core) |
| 6 | `2026-09-06-multi-agent-party.md` | Phase 14 - dynamic party, scheduler, party communication | Frozen (pending Rules Core) |
| 7 | `2026-09-06-agent-memory-pgvector.md` | Phases 15-16 - memory types, pgvector, context builder | Frozen (pending Rules Core) |
| 8 | `2026-09-09-observability.md` | Phase 17 - LLMInvocation telemetry, logging, correlation IDs | Frozen (pending Rules Core) |
| 9 | `2026-09-10-evaluation-design.md` | Phase 18 - evaluation scenarios and metrics | Frozen (pending Rules Core) |
| 10 | `2026-09-13-web-api.md` | Phase 19 - FastAPI adapter, DTOs, idempotency keys | Frozen (pending Rules Core) |
| 11 | `2026-09-13-web-ui.md` | Phase 20 - static web UI over the API | Frozen (pending Rules Core) |
| 12 | `2026-09-13-full-adventure-loop.md` | Phase 21 - locations, travel, scene loop, scene-tagged memory | Frozen (pending Rules Core) |
| 13 | `2026-10-06-rules-core-reprioritisation.md` | Roadmap re-prioritisation: four authority documents + consistency tests | In progress |
| 14 | `<date>-rules-core-r1-grid.md` | R1 Grid & space - battle map, coordinates, distance, reach, cover, line of sight | Planned |
| 15 | `<date>-rules-core-r2-ruleset.md` | R2 Ruleset & data - Ruleset port, `data/rules/*.toml`, loader, SRD NOTICE | Planned |
| 16 | `<date>-rules-core-r3-actions.md` | R3 Actions - resolvers and events for the nine inert actions, bonus/reaction members | Planned |
| 17 | `<date>-rules-core-r4-conditions.md` | R4 Conditions - typed SRD conditions with mechanical effects | Planned |
| 18 | `<date>-rules-core-r5-life-death.md` | R5 Life & death - dying, death saves, stabilization, healing, rests | Planned |
| 19 | `<date>-rules-core-r6-skills.md` | R6 Skills & contests - skills, passive scores, grapple/shove | Planned |
| 20 | `<date>-rules-core-r7-inventory.md` | R7 Inventory - items, equip, armor to AC, consumables, loot, gold | Planned |
| 21 | `<date>-rules-core-r8-progression.md` | R8 Progression - XP, level-up, hit dice, ASI, class features | Planned |
| 22 | `<date>-rules-core-r9-spells.md` | R9 Spellcasting - slots, casting, AoE templates, concentration | Planned |
| 23 | `<date>-rules-core-r10-conformance.md` | R10 Conformance - seeded SRD conformance and coverage report | Planned |
| 24 | `<date>-rules-core-bridge.md` | Bridge - re-integrate agents onto the new interfaces; unpause Part III | Planned |

Rows 14-24 name their plan files as `<date>-rules-core-<id>.md`; the owning plan
substitutes its real `YYYY-MM-DD` date when written. Row 13 is this plan.

## Known documentation gaps (resolve before the corresponding plan)

- Resolved (Plan 2): PostgreSQL test/dev strategy uses `pgserver` (pip-installable,
  root-free, pgvector bundled for Plan 7; session-scoped fixture verified against
  PostgreSQL 16.2); runtime uses `psycopg` 3 + `DATABASE_URL` with plain-SQL
  migrations. CLAUDE.md §36 needed no amendments.
- Resolved (pre-Plan 10): the API/domain-model contract lives at
  `docs/architecture/domain-model-and-api.md` (endpoint schemas, DTO shapes,
  error→HTTP map, idempotency semantics, persistence model). Plan 10 *web-api*
  argues from it. The duplicate `docs/Agentic Conclave-domain-model-and-api.md`
  remains an architecture-overview copy.
- Resolved (Rules Core R2): SRD 5.2 data (weapons, classes, conditions, spells)
  licensing and source-file layout. R2 ships the `Ruleset` port, the
  `data/rules/*.toml` layout, the validating loader, and the CC-BY-4.0 NOTICE;
  every later R-plan adds its own data file there.

## Conventions for all plans

- TDD: every task is test-first, bite-sized steps, frequent commits.
- Conventional commits scoped by architectural layer, e.g. `feat(domain): ...`.
- No LLM, PostgreSQL, FastAPI, or AI-framework dependencies until their phase's plan.
- The domain layer never imports application, AI, infrastructure, or interface code.
