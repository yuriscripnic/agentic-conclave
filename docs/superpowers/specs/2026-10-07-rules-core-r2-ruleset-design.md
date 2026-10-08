# R2 — Ruleset & Data — Design

**Date:** 2026-10-07
**Status:** Approved
**Depends on:** R1 (complete)
**Ships (reprioritisation spec §4):** `Ruleset` port; `data/rules/*.toml` layout +
validating loader; CC-BY-4.0 NOTICE; migrate existing weapon/class/monster
constants. **Exit criterion (LLM-free):** rules data loads from TOML behind the
port; swapping the ruleset id is config-only.

---

## 1. Problem

Rules live as Python constants and inline config tables. `Weapon` dice are
retyped into `config/encounter.toml`, `config/agents.toml` and
`src/session/factory.py`; monsters are inline stat tables in `encounter.toml`;
the 5-10-5 diagonal rule R1 shipped is hardcoded in
`src/domain/space/geometry.py:9`. `CLAUDE.md` §13 requires a ruleset
abstraction (`dnd5e-srd-5.2` is data, not constants) so future rulesets are
possible; the re-prioritisation decision pinned that work at R2, after the
spatial model fixed what the data must describe.

## 2. Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Port shape | `Ruleset` Protocol in `src/domain/rules/ruleset.py`: `ruleset_id`, `weapon(id) -> Weapon`, `statblock(id) -> Statblock`, `character_class(id) -> ClassData`, `diagonal_rule: str` | The queries R3-R9 will need next; nothing speculative beyond them |
| Data layout | `data/rules/<ruleset-id>/{ruleset.toml, weapons.toml, classes.toml, statblocks.toml}` + `data/rules/NOTICE` | One directory per ruleset makes swapping a path choice; NOTICE travels with the data |
| Loader layer | `src/infrastructure/rules/loader.py`; domain consumes the port only | `tomllib` parsing is infrastructure; the domain stays framework-free (CLAUDE.md §4) |
| Selection | `config/game.toml` gains `[ruleset] id = "dnd5e-srd-5.2"`; the session factory loads that directory | Swapping the ruleset id is config-only, per the exit criterion |
| Weapon migration | `WeaponSpec` stays the command carry-type and gains an additive `range_ft: int = 5` (default preserves every existing caller); call sites resolve a `weapon_id` through the ruleset instead of inlining dice | Smallest safe change: `AddCharacterCommand`'s contract is untouched (CLAUDE.md §54), and a non-default range makes the diagonal-rule wiring observable end-to-end |
| Monster migration | `encounter.toml` enemies reference `statblock = "<id>"`; the loader resolves statblocks into `AddCharacterCommand` | Monsters are rules data, not per-encounter config |
| Class migration | `classes.toml` rows validated against the existing `CharacterClass` enum; enum stays authoritative until R8 | R8 owns class features; R2 only moves the data out of constants |
| Diagonal rule | `ruleset.toml [grid] diagonal_rule = "5_10_5"`; `distance_ft` gains a parameter; `CombatEngine` uses the ruleset's value when a board is present | Fulfils R1's explicit deferral; default keeps ungridded combat byte-identical |

## 3. Domain additions

```text
src/domain/rules/ruleset.py     Ruleset protocol
src/domain/rules/statblock.py   Statblock value object (abilities, AC, speed, HP, weapon_id, level)
src/domain/rules/classes.py     ClassData value object (class_id, name, hit_die_size)
src/domain/rules/errors.py      RulesetError, UnknownRuleEntry
```

`Statblock` mirrors today's enemy shape (name, level, six abilities, armor_class,
speed_ft, max_hp, weapon_id) so `application/encounter.py` maps it onto
`AddCharacterCommand` unchanged. `ClassData` carries only `hit_die_size` — R8 adds
features; R2 invents nothing it cannot consume.

## 4. Data files (authored content)

`data/rules/dnd5e-srd-5.2/weapons.toml`: longsword (1d8 slashing, STR, 5 ft),
shortsword (1d6 piercing, Finesse→DEX, 5 ft), mace (1d6 bludgeoning, STR, 5 ft),
scimitar (1d6 slashing, Finesse→DEX, 5 ft), greataxe (1d12 slashing, STR, 5 ft).
Damage types are recorded now (a string column) because R3/R9 consume them;
nothing reads them before then, so the loader validates presence only.

`classes.toml`: fighter d10, rogue d8, wizard d6, cleric d8.

`statblocks.toml`: goblin_scout, goblin_skulker, orc_brute — byte-equivalent to
today's `encounter.toml` enemies (the migration must not change a single roll).

`ruleset.toml`: id `dnd5e-srd-5.2`, name, `[grid] diagonal_rule = "5_10_5"`.

`data/rules/NOTICE`: SRD 5.2 content used under CC-BY-4.0, with attribution to
Wizards of the Coast's SRD 5.2 and a pointer to the licence.

## 5. Wiring

`config/game.toml` gains `[ruleset] id = "dnd5e-srd-5.2"`. The factory resolves
`data/rules/<id>/`, loads the ruleset, and passes it to `GameService`; the
encounter loader and agent profiles take the ruleset and resolve weapon ids.
`CombatEngine.__init__` gains `diagonal_rule: str = "5_10_5"`; `GameService` passes
the ruleset's value so a gridded encounter honours the data file. Without a
ruleset (all existing tests, no-board combat) behaviour is byte-for-byte today's.

## 6. Failure modes

- Unknown weapon/statblock/class id → `UnknownRuleEntry` at resolve time, never a silent default.
- Malformed TOML (wrong type, missing key, unknown die size, dangling weapon_id) → `RulesetError` at load, naming the file and entry.
- Unknown ruleset id in config → `RulesetError` naming the directory it looked for.

## 7. Out of scope

Spell data (R9), condition data (R4), class features/progression tables (R8),
item/armor data (R7), ruleset hot-reload, persistence of the ruleset id.
