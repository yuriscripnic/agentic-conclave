# Rules Core Re-prioritisation — Design

**Date:** 2026-10-06
**Status:** Approved (design); awaiting spec review
**Changes the ordering in:** `docs/superpowers/plans/README.md`, Phases 8+ of
`docs/Agentic Conclave-Implementation Plan.md`, and the Phase 2 line of `CLAUDE.md` §52

---

## 1. Problem

The AI platform (character agent, GM, party, memory, telemetry, evaluation, API,
web UI) was built on top of a rules engine that resolves **exactly one action:
attack**.

Evidence from the current tree:

- `ActionType` (`src/domain/rules/actions.py:12`) declares 12 actions; only
  `ATTACK` has a resolver (`src/domain/combat/engine.py:97`). The other nine are
  enum values with a category and nothing else. `GenericActionProposal` is
  constructed only in tests.
- No spatial model: `grep distance src` returns nothing, and
  `CombatEngine.validate` never checks range. `CLAUDE.md` §2.1 lists "whether a
  target is in range" as a rule the domain must decide; §28 uses "target 100 ft
  away" as its canonical rejection example. Neither is representable.
- Conditions are free-text strings on `Character` with no mechanical effect.
- `apply_healing` has zero callers. `CheckResolver.ability_check` and
  `.saving_throw` have zero callers. `HitPoints.is_defeated` is `hp == 0` for
  everyone: no dying, no death saves, no stabilization.
- The string "spell" does not occur in `src`. Wizard and Cleric are classes with
  no spellcasting.
- Rules are Python constants; `data/` is empty. No `Ruleset` abstraction (§13),
  no SRD 5.2 data layout.

Root cause: "rules engine" was a single plan row, so it was marked complete when
the first playable slice worked. Agentic features were then built against
interfaces a complete rules engine would have changed.

## 2. Decision

**All future work on the AI platform stops until the deterministic rules core is
complete.** The roadmap becomes three parts:

```
Part I    Deterministic core (Plans 1-2)      COMPLETE - unchanged
Part II   RULES CORE  R1..R10 + bridge        the only active work
Part III  AI platform (Plans 3-12)            FROZEN, green, not extended
```

Ordering rule, stated in all three documents: **no Part III work resumes, and no
new agentic plan is written, until R10 and the bridge are done.**

## 3. Decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| Scope of "complete rules engine" | Full SRD rules core: all 12 actions, positioning, conditions, death/dying, skills, inventory, progression, spellcasting, ruleset data, conformance | User selection; matches `CLAUDE.md` §14 Levels 1-5 |
| Spatial model | Grid coordinates, 5-ft squares | User selection; most SRD-faithful, supports AoE templates and cover |
| Fate of existing AI layer | Frozen in place; not deleted, not extended | User selection |
| Freeze contract | **Minimal-adaptation licence** | See §5 |
| Documents changed | `CLAUDE.md` §52, Implementation Plan doc, `plans/README.md`, `README.md` | User selection; all three sources must agree |
| Ruleset/data position | R2, after the grid | Data schema designed once the spatial model is known; R3+ built data-driven rather than constants-then-refactor |

## 4. The Rules Core programme

| # | Sub-project | Depends on | Ships | Exit criterion (LLM-free) |
|---|---|---|---|---|
| R1 | Grid & space | — | 5-ft square battle map, coordinates, distance in feet (5e diagonal rule), occupied squares, reach, cover (+2/+5 AC), line-of-sight validation | An attacker out of LoS or behind cover resolves deterministically; §28's "target 100 ft away" reproduces exactly |
| R2 | Ruleset & data | R1 | `Ruleset` port; `data/rules/*.toml` layout + validating loader; CC-BY-4.0 NOTICE; migrate existing weapon/class/monster constants | Rules data loads from TOML behind the port; swapping ruleset id is config-only |
| R3 | Actions | R1, R2 | Resolvers + events for the nine inert actions; `BONUS_ACTION`/`REACTION` get real members (off-hand attack, opportunity attack) | Every `ActionType` member has a resolver, events and a CLI path; no dead enum values |
| R4 | Conditions | R2, R3 | Typed SRD condition set with an effects table applied at the correct resolution points; application, removal, recovery | Every condition alters rolls/movement/actions per SRD 5.2, tested per condition |
| R5 | Life & death | R4 | 0 HP -> unconscious, death saves (3/3), damage-at-0, massive damage, stabilization, healing, short/long rests | Full down-and-recover cycle deterministic and replayable |
| R6 | Skills & contests | R4 | Skill list, proficiency, passive scores, contested checks (grapple/shove) | `CheckResolver`'s check/save paths reachable from real actions |
| R7 | Inventory | R2 | Item/armor models, equip/unequip, armor -> AC, consumables, loot, gold, carry capacity | Inventory is playable state, not persistence-only |
| R8 | Progression | R2 | XP thresholds, level-up, hit dice, ASI, class features for Fighter/Rogue/Wizard/Cleric | A character levels 1 -> 20 deterministically |
| R9 | Spellcasting | R1, R4, R7 | Spell model, slots, known/prepared, cantrips, spell attacks and saves, grid AoE templates, concentration, rituals. Phased: 9a slots+damage, 9b control/concentration, 9c utility/rituals, 9d full four-class SRD list | Wizard and Cleric play by SRD spell rules against the grid |
| R10 | Conformance | all | Seeded SRD conformance + property suite; rules-coverage report | Suite is the gate; no LLM anywhere in it |
| B | Bridge | R10 | Update `ai/` perception, context and tools to the new interfaces; unpause Part III | Agent suite green against grid + conditions + spells |

R1 is first because it is the interface spine; R9 is last because magic depends on
space (AoE), conditions and items (components). Each R-row ends in a runnable CLI
milestone with tests, matching the existing 12-plan series shape.

## 5. Freeze contract (minimal-adaptation licence)

Part III is frozen: no new agent capability, no new agent behaviour, no new
agentic plan. When an R-plan changes a domain interface the agent layer reads,
the `ai/` adapter is updated **only enough to compile and keep its existing tests
passing**. Learning to *use* grids, cover, conditions and spells is the bridge
plan (B), not Part II work.

This keeps the 605-test suite continuously green during Part II, at the cost of
some ongoing `ai/` churn. It is preferred over a strict freeze, which would leave
the agent suite red from R1 until B.

## 6. Exit criteria for Part II

- Every `ActionType` member has a resolver, events, and a CLI path.
- Every SRD condition has a tested mechanical effect.
- Positioning, cover and line of sight are validated by the engine, never
  inferred from a prompt.
- Spells for the four classes resolve through slots, saves/attacks and grid
  templates.
- Rules data lives in `data/rules/` behind a `Ruleset` port; `dnd5e-srd-5.2` is
  data, not constants.
- The conformance suite passes seeded and offline, with no LLM in the domain path.
- `ruff`, `mypy --strict` and the full suite are green; every R-plan has tests.

## 7. Document changes

| File | Change |
|---|---|
| `CLAUDE.md` | §52: expand the one-line "Phase 2 - Rules engine" into R1-R10; add the gate that Phases 6-13 do not resume until Part II exits. §14 Levels 1-5 name the missing pieces (conditions, positioning, death, spells, ruleset data). |
| `docs/Agentic Conclave-Implementation Plan.md` | Restructure into Part I / Part II / Part III; R1-R10 as new sections between the deterministic core and the AI phases; AI phases marked complete-but-frozen with the gate restated. |
| `docs/superpowers/plans/README.md` | Rows 1-2 stay `Complete`; rows 3-12 -> `Frozen (pending Rules Core)`; new rows 13-24: this re-prioritisation plan (13), R1-R10 (14-23), the Bridge (24). "Known documentation gaps": SRD 5.2 data layout resolved by R2. |
| `README.md` | Add a status/roadmap section pointing at the plans table. |

## 8. Risks

- **Scope.** Full SRD spellcasting (R9d) is the largest single sub-project; it is
  phased so 9a already delivers playable magic.
- **Frozen drift.** Minimal adaptation can quietly grow into feature work; the
  bridge plan is the only place agent behaviour changes.
- **Renumbering.** R-numbers are new; Part III keeps its existing plan numbers 3-12
  so old commits and cross-references stay valid.

## 9. Non-goals

- No change to Part I (deterministic core) or to Part III's existing code.
- No new AI/infrastructure dependencies.
- Phase 21 "advanced features" (dynamic world generation, factions, economy,
  model routing, distributed workers) stays postponed; it is not part of Part II.
