# Rules Core Re-prioritisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-order the project roadmap so the complete deterministic rules core (R1-R10) ships before any further AI-platform work, and pin that ordering with a test so it cannot silently drift back.

**Architecture:** Four documents are the authorities on phase order. Each is edited to state the same Part I/II/III structure and the same canonical gate sentence. A new `tests/docs/test_roadmap_consistency.py` asserts the shared strings, so a future edit to one document alone fails the suite.

**Tech Stack:** Python 3.12, pytest (existing), Markdown. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-06-rules-core-reprioritisation-design.md`

## Global Constraints

- Canonical gate sentence, copied byte-for-byte into the three documents that carry the ordering rule per spec §2 (`CLAUDE.md`, `docs/Agentic Conclave-Implementation Plan.md`, `docs/superpowers/plans/README.md`): `PART II GATE: No Part III work resumes, and no new agentic plan is written, until R10 and the Bridge are complete.`
- Rules Core identifiers and names, in this exact order: `R1 Grid & space`, `R2 Ruleset & data`, `R3 Actions`, `R4 Conditions`, `R5 Life & death`, `R6 Skills & contests`, `R7 Inventory`, `R8 Progression`, `R9 Spellcasting`, `R10 Conformance`.
- Plan rows: this re-prioritisation plan is plan 13; R1-R10 are plans 14-23; the Bridge is plan 24.
- Part III keeps its existing plan numbers 3-12. Do not renumber them; old commits and cross-references depend on them.
- Part II frozen status string, exact: `Frozen (pending Rules Core)`.
- `ruff`, `mypy --strict` and the full suite must stay green. New tests live under `tests/`.
- Do not modify any file under `src/`. This plan changes documentation and adds tests only.

## Review Focus

The spec is a vision document; its silence is not permission for a defect. These are the failure modes most likely to bite a reader of these documents, each pinned by a test in the owning task below.

- **Partial edit.** A contributor updates one authority document and forgets the other three, so the roadmap disagrees with itself. Pinned by the three independent document tests (Tasks 1-4).
- **Silent re-ordering.** Someone moves ruleset/data back behind actions (or grid behind ruleset) in one document only. Pinned by the ordered-row assertion in Task 1.
- **Gate erosion.** The freeze sentence is paraphrased or its wording drifts, weakening the gate. Pinned by an exact-string assertion in each of the three documents that carry it.
- **Frozen status lost.** A Part III row is edited back to `In-progress` while Part II is unfinished. Pinned by the frozen-status assertion in Task 1.
- **Stale root README.** A new reader takes the README's MVP framing at face value and never finds the roadmap. Pinned by Task 4.

---

### Task 1: Rewrite the plans README and pin it

**Files:**
- Modify: `docs/superpowers/plans/README.md`
- Test: `tests/docs/test_roadmap_consistency.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: the canonical strings every later task reuses: the gate sentence, the ten `R<n> <Name>` row labels in order, and the `Frozen (pending Rules Core)` status string. Tasks 2-4 assert the same constants against their own documents.

- [ ] **Step 1: Write the failing test**

```python
# tests/docs/test_roadmap_consistency.py
"""The roadmap ordering is stated in four documents; these tests keep them agreeing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS_README = ROOT / "docs/superpowers/plans/README.md"

GATE = (
    "PART II GATE: No Part III work resumes, and no new agentic plan is "
    "written, until R10 and the Bridge are complete."
)

FREEZE = (
    "FROZEN ADAPTER LICENCE: Part III adapters may be updated only enough to "
    "keep the existing suite green; no new agent capability is added until the "
    "Bridge."
)

RULES_CORE_ROWS = [
    "R1 Grid & space",
    "R2 Ruleset & data",
    "R3 Actions",
    "R4 Conditions",
    "R5 Life & death",
    "R6 Skills & contests",
    "R7 Inventory",
    "R8 Progression",
    "R9 Spellcasting",
    "R10 Conformance",
]

FROZEN = "Frozen (pending Rules Core)"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plans_readme_states_the_gate() -> None:
    assert GATE in _read(PLANS_README)


def test_plans_readme_lists_rules_core_in_order() -> None:
    text = _read(PLANS_README)
    positions = [text.index(row) for row in RULES_CORE_ROWS]
    assert positions == sorted(positions)


def test_plans_readme_freezes_part_three() -> None:
    assert FROZEN in _read(PLANS_README)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: 3 failed (the strings are not in the README yet).

- [ ] **Step 3: Rewrite the plan table in `docs/superpowers/plans/README.md`**

Replace the existing "Plan series" table with this one, and insert the gate paragraph immediately above it:

```markdown
> **PART II GATE: No Part III work resumes, and no new agentic plan is written, until R10 and the Bridge are complete.**

**Part I - Deterministic core.** Plans 1-2. Complete; unchanged.

**Part II - Rules Core (R1-R10) + Bridge.** The only active work. Rows 13-23.

**Part III - AI platform.** Plans 3-12. Frozen; green; not extended until Part II exits.

| # | Plan file | Covers | Status |
|---|-----------|--------|--------|
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
```

Rows 14-24 name their plan files as `<date>-rules-core-<id>.md`; the owning plan substitutes its real `YYYY-MM-DD` date when written. Row 13 is this plan.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/README.md tests/docs/test_roadmap_consistency.py
git commit -m "docs(plans): reframe roadmap as Parts I-III with Rules Core gate"
```

---

### Task 2: Expand `CLAUDE.md` §52 and state the gate

**Files:**
- Modify: `CLAUDE.md` (§14 Levels 1-5, §52 Phase 2 block)
- Test: `tests/docs/test_roadmap_consistency.py` (modify)

**Interfaces:**
- Consumes: the `GATE` and `RULES_CORE_ROWS` constants written in Task 1.
- Produces: nothing new; this task only adds assertions.

- [ ] **Step 1: Write the failing test**

Append to `tests/docs/test_roadmap_consistency.py`:

```python
CLAUDE_MD = ROOT / "CLAUDE.md"


def test_claude_md_states_the_gate() -> None:
    assert GATE in _read(CLAUDE_MD)


def test_claude_md_expands_phase_2_into_the_rules_core() -> None:
    text = _read(CLAUDE_MD)
    positions = [text.index(row) for row in RULES_CORE_ROWS]
    assert positions == sorted(positions)


def test_claude_md_states_the_freeze_licence() -> None:
    assert FREEZE in _read(CLAUDE_MD)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: the three new tests fail; Task 1's three still pass.

- [ ] **Step 3: Expand the `### Phase 2` block in `CLAUDE.md` §52**

Replace the existing Phase 2 block (the `Rules engine:` heading and its ```text fence```) with:

```markdown
### Phase 2 — Rules Engine (the Rules Core programme, R1-R10)

Phase 2 is a programme, not a single step. It is not complete until R10 and the
Bridge are done. Listed in dependency order:

```text
R1  Grid & space          battle map, coordinates, distance, reach, cover, line of sight
R2  Ruleset & data        Ruleset port, data/rules/*.toml, loader, SRD 5.2 NOTICE
R3  Actions               resolvers + events for all ActionType members
R4  Conditions            typed SRD conditions with mechanical effects
R5  Life & death          dying, death saving throws, stabilization, healing, rests
R6  Skills & contests     skills, passive scores, grapple/shove
R7  Inventory             items, equip, armor to AC, consumables, loot, gold
R8  Progression           XP, level-up, hit dice, ASI, class features
R9  Spellcasting          slots, casting, grid AoE templates, concentration
R10 Conformance           seeded SRD conformance suite and coverage report
Bridge                    re-integrate agents; unpause Phases 6-13
```

> **PART II GATE: No Part III work resumes, and no new agentic plan is written, until R10 and the Bridge are complete.**

> **FROZEN ADAPTER LICENCE: Part III adapters may be updated only enough to keep the existing suite green; no new agent capability is added until the Bridge.**
```

Then, in §14, extend the Level 1-5 lists so each missing rule is named: add `positioning`, `cover`, `line of sight` to Level 1; `dash`, `dodge`, `disengage`, `help`, `hide`, `ready`, `search`, `use item` are already listed and stay; add `death saving throws`, `stabilization`, `rests` to Level 3; add `skills`, `contests` to Level 2; add `inventory use`, `equipment` to Level 1; and add to Level 5 that the spell list is data-driven from `data/rules/`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md tests/docs/test_roadmap_consistency.py
git commit -m "docs(claude-md): expand Phase 2 into the Rules Core programme with gate"
```

---

### Task 3: Restructure the Implementation Plan into Parts I-III

**Files:**
- Modify: `docs/Agentic Conclave-Implementation Plan.md`
- Test: `tests/docs/test_roadmap_consistency.py` (modify)

**Interfaces:**
- Consumes: the `GATE` constant from Task 1.
- Produces: nothing new; assertions only.

- [ ] **Step 1: Write the failing test**

Append to `tests/docs/test_roadmap_consistency.py`:

```python
IMPL_PLAN = ROOT / "docs/Agentic Conclave-Implementation Plan.md"


def test_implementation_plan_states_the_gate() -> None:
    assert GATE in _read(IMPL_PLAN)


def test_implementation_plan_has_three_parts() -> None:
    text = _read(IMPL_PLAN)
    for heading in ("Part I", "Part II", "Part III"):
        assert heading in text


def test_implementation_plan_marks_part_three_frozen() -> None:
    assert FROZEN in _read(IMPL_PLAN)


def test_implementation_plan_states_the_freeze_licence() -> None:
    assert FREEZE in _read(IMPL_PLAN)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: the four new tests fail; the previous six still pass.

- [ ] **Step 3: Restructure the document**

Immediately after the document's intro (before "## 3. Phase 0"), insert a new section:

```markdown
# Roadmap Structure

The phases below are grouped into three parts.

**Part I - Deterministic core.** Phases 0-7. Complete.

**Part II - Rules Core.** The R1-R10 programme plus the Bridge. This is the only
active work. Phase 2 in `CLAUDE.md` §52 is this programme; it is not complete
until R10 and the Bridge are done.

> **PART II GATE: No Part III work resumes, and no new agentic plan is written, until R10 and the Bridge are complete.**

**Part III - AI platform.** Phases 8-21. Built and tested, but **Frozen (pending
Rules Core)**.

> **FROZEN ADAPTER LICENCE: Part III adapters may be updated only enough to keep the existing suite green; no new agent capability is added until the Bridge.**
```

Then add `(Part III — Frozen (pending Rules Core))` to each of the Phase 8-21 headings, and add new sections for R1-R10 before Phase 8, copying the goal/exit criteria rows from the spec's §4 table.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add "docs/Agentic Conclave-Implementation Plan.md" tests/docs/test_roadmap_consistency.py
git commit -m "docs(plan): restructure implementation plan into Parts I-III"
```

---

### Task 4: Point the root README at the roadmap

**Files:**
- Modify: `README.md`
- Test: `tests/docs/test_roadmap_consistency.py` (modify)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new; assertions only.

- [ ] **Step 1: Write the failing test**

Append to `tests/docs/test_roadmap_consistency.py`:

```python
ROOT_README = ROOT / "README.md"


def test_root_readme_points_at_the_roadmap() -> None:
    text = _read(ROOT_README)
    assert "docs/superpowers/plans/README.md" in text
    assert "Rules Core" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: the new test fails; the previous ten still pass.

- [ ] **Step 3: Add a status section**

Insert immediately after the README's opening paragraph:

```markdown
## Project status

The **deterministic rules core is the current focus**. AI-platform work (agents,
GM, memory, telemetry, evaluation, API, web UI) is built and tested but frozen
until the rules core is complete. See the roadmap in
[`docs/superpowers/plans/README.md`](docs/superpowers/plans/README.md).
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/docs/test_roadmap_consistency.py -v`
Expected: 11 passed.

- [ ] **Step 5: Run the full gate and commit**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
git add README.md tests/docs/test_roadmap_consistency.py
git commit -m "docs(readme): add roadmap status section"
```

Expected: full suite green (605 prior + 11 new), ruff clean, mypy clean.

---
