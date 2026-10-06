# R1 — Grid & Space: Design

**Date:** 2026-10-06
**Status:** Approved (design); awaiting spec review
**Programme:** Rules Core R1 of the plan in
`docs/superpowers/specs/2026-10-06-rules-core-reprioritisation-design.md` (§4, row R1)
**Depends on:** nothing (first R-plan); consumed by R3 (actions/movement), R9 (AoE), Bridge

---

## 1. Problem

The rules engine resolves attacks with no spatial model. `CombatEngine.validate`
checks turn, action availability, weapon and target validity, but never range:
a character can hit a target an arbitrary distance away. `CLAUDE.md` §2.1 lists
"whether a target is in range" as a rule the domain must decide, and §28 uses
"target 100 ft away" as its canonical rejection example. Neither is
representable today, and R9's area-of-effect spells and R3's movement need
positions to exist first.

## 2. Decisions taken

| Decision | Choice | Source |
|---|---|---|
| Spatial model | Grid coordinates, 5-ft squares | Programme spec §3 (user selection) |
| Diagonal distance | 5-10-5 alternating (an optional variant in SRD 5.2, whose default is 5 ft per diagonal) | User selection, confirmed against SRD 5.2 |
| Line of sight | Corner-to-corner, SRD style | User selection |
| Board adoption | Optional in domain; encounter ships a map; mandatory at the Bridge | User selection |
| Board location | Combat-scoped value object + pure geometry functions (Approach A) | This spec |
| Map format | TOML under `config/maps/` | Conventional default; world data, not R2's rules data |
| Cover tiers | HALF +2 AC, THREE_QUARTERS +5 AC, TOTAL blocks targeting | SRD structure named in programme spec §4 |
| Spawn assignment | Participant-list order onto per-side spawn squares | Deterministic default |

## 3. Domain package: `src/domain/space/`

Three small modules, each one responsibility.

### `square.py`

`Square(x, y)` — frozen value object, non-negative ints. No board knowledge; a
square's bounds are checked against a board, not against itself.

### `board.py`

`Board(width, height, walls: frozenset[Square], cover: dict[Square, CoverLevel])`
— frozen value object.

- `CoverLevel` StrEnum: `NONE`, `HALF`, `THREE_QUARTERS`, `TOTAL`.
- `__post_init__` validates: positive width/height; every wall and cover square
  in bounds; no wall carries cover (a wall is not a cover object); no duplicate
  cover squares (dict keys make this structural, but the loader must reject
  duplicates rather than silently overwrite).
- Accessors: `in_bounds(square)`, `is_wall(square)`, `cover_at(square)`,
  `squares()` for rendering.

### `geometry.py`

Pure functions over a board; no engine, no events, no state.

- `distance_ft(a: Square, b: Square) -> int` — 5-10-5: walk the Chebyshev path;
  each diagonal step costs 5, then 10, alternating; straight steps cost 5.
  (0,0) to (2,1) is 15 ft.
- `line_of_sight(board, a, b) -> bool` — 16 segments (4 corners of a's square x
  4 corners of b's square); sight exists if at least one segment touches no
  wall. **Edge rule (explicit, so peeking works):** a wall blocks a segment if
  the segment intersects the wall cell's area *excluding the wall's four corner
  points* — a line grazing only a wall's corner is clear.
- `cover_between(board, a, b) -> CoverLevel` — count how many of those 16
  segments are blocked by walls: all blocked -> `TOTAL` (and `line_of_sight` is
  false anyway); none blocked -> the target square's own cover flag; some
  blocked -> at least `HALF`, upgraded to the target's flag if the flag is
  higher.

## 4. Combat integration

`Combat` (`src/domain/combat/state.py`) gains two fields with defaults, so every
existing constructor call is unchanged:

```python
board: Board | None = None
positions: dict[CharacterId, Square] = field(default_factory=dict)
```

`CombatEngine.start` — when a board is provided, assign spawn squares in
participant-list order (party ids onto the party spawn list, enemy ids onto the
enemy spawn list) and reject with `ValidationError` when there are more
participants than spawn squares. Positions are written only here and by later
movement rules; nothing else mutates them.

`CombatEngine.validate` — with a board present, after the existing checks, in
order:

1. `distance_ft(actor_sq, target_sq) <= weapon.range_ft`, else reject
   `("target is out of range", "out_of_range")`.
2. `line_of_sight(board, actor_sq, target_sq)`, else reject
   `("no line of sight to target", "no_line_of_sight")`.
3. `cover_between(board, actor_sq, target_sq)` is not `TOTAL`, else reject
   `("target has total cover", "total_cover")`.

On a hit, the attack roll is made against
`target.armor_class + 2` (HALF) or `+ 5` (THREE_QUARTERS). Damage is unchanged.
Without a board, none of this runs — behaviour is byte-for-byte today's.

## 5. Config

`config/maps/eastern_tower.toml`:

```toml
[map]
name = "Eastern Tower"
width = 10
height = 10

walls = [[4, 0], [5, 0], [6, 0], [0, 5]]

[[cover]]
square = [3, 4]
level = "half"

[spawns.party]
squares = [[1, 1], [2, 1], [1, 2], [2, 2]]

[spawns.enemies]
squares = [[8, 8], [7, 8], [8, 7]]
```

`config/encounter.toml` gains `map = "eastern_tower"`. Binding maps to
arbitrary world locations is later work; the encounter owns its map for now.

## 6. Views and CLI

`CombatView` gains an optional `positions: dict[str, tuple[int, int]] | None`.
The CLI renderer draws a small ASCII map during combat: `#` wall, `@` party,
first letter of the enemy name, `.` empty. The renderer is interface-layer and
must not compute geometry — it renders what the view carries.

## 7. Persistence

The Postgres mapping (`src/infrastructure/persistence/postgres/mapping.py`)
must serialize and restore `board` and `positions` inside the existing JSONB
state document, or a saved game loses its map. In-memory storage holds the
object graph directly and needs nothing.

## 8. Testing

- `tests/domain/test_square.py` — construction, validation, equality.
- `tests/domain/test_board.py` — bounds, wall/cover validation, accessors.
- `tests/domain/test_geometry.py` — table-driven distance (straight, diagonal,
  mixed); LoS table tests (open room visible, wall between blocked, peeking
  corner visible, wall-corner graze clear); cover (target flag, none blocked
  keeps flag, partial obstruction grants at least HALF, all blocked TOTAL).
- `tests/domain/test_combat.py` (extend) — with a board: each reject code
  (`out_of_range`, `no_line_of_sight`, `total_cover`); a seeded test where HALF
  cover's +2 flips a hit into a miss; spawn over-capacity rejected; no board =
  existing behaviour unchanged.
- `tests/infrastructure/test_postgres_mapping.py` (extend) — board and
  positions round-trip.
- `tests/interfaces/test_cli.py` (extend) — the map renders during combat.
- Full suite green; `ruff` and `mypy --strict` clean.

## 9. Non-goals

- Ranged-weapon range bands and long-range disadvantage (R3/R9); R1 uses
  melee `weapon.range_ft` only.
- Difficult terrain, movement cost, paths — R3 consumes the primitives.
- Opportunity attacks, large creatures, squeezing, AoE templates, fog and
  hidden creatures, per-location map binding.

## 10. Risks

- **Corner-to-corner geometry** is where subtle bugs hide. The explicit
  corner-graze rule and table tests are the mitigation; if the geometry test
  set grows unwieldy, that is a signal to stop and simplify the rule, not the
  tests.
- **Optional boards rotting into never-used.** Mitigated by the encounter
  config shipping a map and an integration test exercising it.
- **5-10-5 is an optional rule in SRD 5.2.** Confirmed during design (user's
  web-sourced summary): SRD 5.2's default counts every diagonal as 5 ft, with
  5-10-5 as an explicitly supported optional variant for geometric realism.
  This ruleset deliberately ships 5-10-5 (user choice). R2 makes the rule a
  `data/rules/` parameter, so switching to the 5.2 default later is
  configuration, not a rewrite.
