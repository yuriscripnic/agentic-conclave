# Agentic Conclave — Implementation Plan Roadmap

This directory contains the executable implementation plans for the Agentic Conclave
Multi-Agent RPG. Plans are derived from, and must not contradict:

- `CLAUDE.md` — development rules (source-of-truth priority #3)
- `docs/Agentic Conclave-Implementation Plan.md` — phase sequence (source-of-truth priority #4-ish, per its §29)
- `docs/Agentic Conclave-architecture-overview.md` — architecture baseline

## Plan series

Each plan produces working, testable software on its own and follows the phase order
mandated by the Implementation Plan document.

> **Numbering note:** session shorthand for the 2026-09-06 work called the party
> plan "Plan 5" and the agent-memory plan "Plan 6". The canonical numbers are the
> table rows below (party = #6, memory = #7); the Status column is the authority
> on what has shipped.

| # | Plan file | Covers (Implementation Plan doc) | Status |
|---|-----------|----------------------------------|--------|
| 1 | `2026-09-03-deterministic-core-mvp0.md` | Phases 0–7 — Repository bootstrap, domain primitives, dice, checks, actions, combat, events, first playable CLI (**MVP-0**) | Complete |
| 2 | `2026-09-04-persistence-postgres.md` | Phase 8 — PostgreSQL repositories, transactions, optimistic locking | Complete |
| 3 | `2026-09-04-model-gateway.md` | Phases 9–10 — `ModelGateway` abstraction + `FakeModelGateway`, model profiles, OpenRouter adapter | Complete |
| 4 | `2026-09-05-character-agent.md` | Phases 11–12 — first character agent, decision pipeline, bounded retry, deterministic fallback | Complete |
| 5 | `2026-09-08-gm-agent.md` | Phase 13 — GM agent with narration + NPC talk behind the rules engine (`--gm off\|llm\|fake`, notable-events cadence, `say` verb) | Complete |
| 6 | `2026-09-06-multi-agent-party.md` | Phase 14 — dynamic party, agent scheduler, public party communication | Complete |
| 7 | `2026-09-06-agent-memory-pgvector.md` | Phases 15–16 — working/episodic/semantic memory, pgvector, context builder | Complete |
| 8 | `2026-09-09-observability.md` | Phase 17 — `LLMInvocation` telemetry, structured logging, correlation IDs | Complete |
| 9 | `2026-09-10-evaluation-design.md` | Phase 18 — repeatable evaluation scenarios and metrics | Complete |
| 10 | *web-api* | Phase 19 — FastAPI adapter, DTOs, idempotency keys | Not written |
| 11 | *web-ui* | Phase 20 — Web UI consuming the application/API layer | Not written |

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
- SRD 5.2 data (weapons, classes, spells) licensing/source file layout is undefined;
  Plan 1 keeps rule data as Python constants and later plans must introduce `data/rules/`.

## Conventions for all plans

- TDD: every task is test-first, bite-sized steps, frequent commits.
- Conventional commits scoped by architectural layer, e.g. `feat(domain): ...`.
- No LLM, PostgreSQL, FastAPI, or AI-framework dependencies until their phase's plan.
- The domain layer never imports application, AI, infrastructure, or interface code.
