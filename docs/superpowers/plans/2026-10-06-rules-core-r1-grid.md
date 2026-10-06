# R1 — Grid & Space Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the rules engine a spatial model — battle map, coordinates, distance, reach, cover and line of sight — so range validation is decided by the domain, not assumed away.

**Architecture:** A new `domain/space/` package holds `Square`, `Board` (walls + cover terrain) and pure geometry functions. `Combat` gains an optional board and positions; `CombatEngine.validate` consults geometry only when a board is present, so combat without a map is byte-for-byte today's behaviour. A TOML loader in the application layer feeds the shipped encounter its map.

**Tech Stack:** Python 3.12 stdlib only (dataclasses, enum, math). No new dependencies. pytest, ruff, mypy --strict as today.

**Spec:** `docs/superpowers/specs/2026-10-06-rules-core-r1-grid-design.md`

## Global Constraints

- The domain package `src/domain/space/` imports nothing from application, ai, infrastructure or interfaces (CLAUDE.md §4).
- The board is optional: `Combat.board: Board | None = None`. Without a board, combat behaviour is byte-for-byte unchanged (spec §4).
- Diagonal distance is 5-10-5 alternating — an optional variant in SRD 5.2, whose default is 5 ft per diagonal; becomes a `data/rules/` parameter at R2 (spec §2, §10).
- Line of sight is corner-to-corner over 16 segments; a wall blocks a segment if it intersects the wall cell's area **excluding the wall's four corner points** (spec §3).
- Cover: `HALF` +2 AC, `THREE_QUARTERS` +5 AC, `TOTAL` blocks targeting (spec §2, §4).
- Reject codes, exact strings: `out_of_range`, `no_line_of_sight`, `total_cover`.
- FROZEN ADAPTER LICENCE: no new agent capability; `ai/` is touched only if a test forces it.
- No persistence change (spec §7): combat is transient in `GameService._combats`.
- No new dependencies; `ruff` clean; `mypy --strict` clean; full suite green at every task's end.

## Review Focus

The spec implies these failure modes but no single task's tests exercise all of them; each line is pinned by the named test.

- **Corner-graze ambiguity.** A line touching only a wall's corner point must be clear, not blocked — this is what makes peeking work. Pinned by Task 3's graze test.
- **Optional-board rot.** A game opened without a board must reject nothing new and roll identically. Pinned by Task 6's no-board regression test.
- **Spawn over-capacity.** More participants than spawn squares must raise, not silently leave someone unpositioned. Pinned by Task 5.
- **Cover double-counting.** Cover must change only the target's effective AC, never the attacker's roll bonus, and never apply to a rejected attack. Pinned by Task 6's seeded flip test.
- **Silent ungridded combat.** An encounter naming a missing or malformed map must fail at load, not start combat ungridded. Pinned by Task 8.

---

### Task 1: Spatial value objects — Square, CoverLevel, Board

**Files:**
- Create: `src/domain/space/__init__.py` (empty)
- Create: `src/domain/space/square.py`
- Create: `src/domain/space/board.py`
- Test: `tests/domain/test_square.py`, `tests/domain/test_board.py`

**Interfaces:**
- Consumes: `domain.common.errors.ValidationError` (existing).
- Produces, for every later task: `Square(x: int, y: int)` frozen, non-negative, hashable, ordered; `CoverLevel` StrEnum `NONE|HALF|THREE_QUARTERS|TOTAL`; `higher_cover(a, b) -> CoverLevel`; `Board(width: int, height: int, walls: frozenset[Square], cover: dict[Square, CoverLevel])` frozen with `in_bounds(square) -> bool`, `is_wall(square) -> bool`, `cover_at(square) -> CoverLevel`.

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_square.py`:

```python
import pytest

from domain.common.errors import ValidationError
from domain.space.square import Square


def test_square_holds_coordinates_and_compares() -> None:
    assert Square(2, 3) == Square(2, 3)
    assert Square(1, 5) < Square(2, 5)
    assert hash(Square(1, 1)) == hash(Square(1, 1))


@pytest.mark.parametrize("x,y", [(-1, 0), (0, -1)])
def test_negative_coordinates_rejected(x: int, y: int) -> None:
    with pytest.raises(ValidationError):
        Square(x, y)
```

`tests/domain/test_board.py`:

```python
import pytest

from domain.common.errors import ValidationError
from domain.space.board import Board, CoverLevel, higher_cover
from domain.space.square import Square


def test_board_accessors() -> None:
    board = Board(
        width=3,
        height=3,
        walls=frozenset({Square(0, 0)}),
        cover={Square(2, 2): CoverLevel.HALF},
    )
    assert board.in_bounds(Square(2, 2))
    assert not board.in_bounds(Square(3, 0))
    assert board.is_wall(Square(0, 0))
    assert not board.is_wall(Square(1, 1))
    assert board.cover_at(Square(2, 2)) is CoverLevel.HALF
    assert board.cover_at(Square(1, 1)) is CoverLevel.NONE


def test_wall_outside_board_rejected() -> None:
    with pytest.raises(ValidationError):
        Board(width=2, height=2, walls=frozenset({Square(2, 0)}))


def test_wall_cannot_carry_cover() -> None:
    with pytest.raises(ValidationError):
        Board(
            width=2,
            height=2,
            walls=frozenset({Square(0, 0)}),
            cover={Square(0, 0): CoverLevel.HALF},
        )


def test_cover_level_none_rejected() -> None:
    with pytest.raises(ValidationError):
        Board(width=2, height=2, cover={Square(0, 0): CoverLevel.NONE})


def test_higher_cover_returns_the_more_severe_level() -> None:
    assert higher_cover(CoverLevel.NONE, CoverLevel.HALF) is CoverLevel.HALF
    assert higher_cover(CoverLevel.THREE_QUARTERS, CoverLevel.HALF) is (
        CoverLevel.THREE_QUARTERS
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_square.py tests/domain/test_board.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.space'`.

- [ ] **Step 3: Write the minimal implementation**

`src/domain/space/__init__.py`: empty file.

`src/domain/space/square.py`:

```python
"""Grid squares: the address of one 5-ft cell on a battle map (R1 spec §3)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError


@dataclass(frozen=True, order=True)
class Square:
    x: int
    y: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValidationError(
                f"square coordinates must be non-negative, got ({self.x}, {self.y})"
            )
```

`src/domain/space/board.py`:

```python
"""Battle boards: walls and cover terrain over a grid of squares (R1 spec §3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.common.errors import ValidationError
from domain.space.square import Square


class CoverLevel(StrEnum):
    NONE = "none"
    HALF = "half"
    THREE_QUARTERS = "three_quarters"
    TOTAL = "total"


SEVERITY: tuple[CoverLevel, ...] = (
    CoverLevel.NONE,
    CoverLevel.HALF,
    CoverLevel.THREE_QUARTERS,
    CoverLevel.TOTAL,
)


def higher_cover(a: CoverLevel, b: CoverLevel) -> CoverLevel:
    """The more severe of two cover levels (enum members do not order by value)."""
    return a if SEVERITY.index(a) >= SEVERITY.index(b) else b


@dataclass(frozen=True)
class Board:
    width: int
    height: int
    walls: frozenset[Square] = frozenset()
    cover: dict[Square, CoverLevel] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValidationError("board dimensions must be positive")
        for square in self.walls:
            self._check(square, "wall")
        for square, level in self.cover.items():
            self._check(square, "cover")
            if square in self.walls:
                raise ValidationError(f"wall square {square} cannot carry cover")
            if level is CoverLevel.NONE:
                raise ValidationError("cover squares must carry a non-NONE level")

    def _check(self, square: Square, what: str) -> None:
        if not self.in_bounds(square):
            raise ValidationError(f"{what} square {square} is outside the board")

    def in_bounds(self, square: Square) -> bool:
        return 0 <= square.x < self.width and 0 <= square.y < self.height

    def is_wall(self, square: Square) -> bool:
        return square in self.walls

    def cover_at(self, square: Square) -> CoverLevel:
        return self.cover.get(square, CoverLevel.NONE)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_square.py tests/domain/test_board.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/space tests/domain/test_square.py tests/domain/test_board.py
git commit -m "feat(domain): add Square, CoverLevel and Board spatial value objects"
```

---

### Task 2: Distance in feet — the 5-10-5 diagonal rule

**Files:**
- Create: `src/domain/space/geometry.py`
- Test: `tests/domain/test_geometry.py`

**Interfaces:**
- Consumes: `Square` (Task 1).
- Produces: `distance_ft(a: Square, b: Square) -> int` — every later task and R3's movement rules call this.

- [ ] **Step 1: Write the failing test**

`tests/domain/test_geometry.py`:

```python
import pytest

from domain.space.geometry import distance_ft
from domain.space.square import Square


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (Square(0, 0), Square(0, 0), 0),
        (Square(0, 0), Square(3, 0), 15),   # straight only
        (Square(0, 0), Square(1, 1), 5),    # first diagonal = 5
        (Square(0, 0), Square(2, 2), 15),   # second diagonal = 10
        (Square(0, 0), Square(3, 1), 15),   # 1 diagonal + 2 straight
        (Square(0, 0), Square(4, 2), 25),   # 2 diagonals (15) + 2 straight (10)
        (Square(0, 0), Square(20, 0), 100), # the §28 example, verbatim
    ],
)
def test_distance_uses_the_5_10_5_rule(a: Square, b: Square, expected: int) -> None:
    assert distance_ft(a, b) == expected


def test_distance_is_symmetric() -> None:
    assert distance_ft(Square(0, 0), Square(3, 2)) == distance_ft(
        Square(3, 2), Square(0, 0)
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.space.geometry'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/domain/space/geometry.py` (create the file):

```python
"""Pure spatial geometry over a board: distance, line of sight, cover (R1 spec §3)."""

from __future__ import annotations

from domain.space.square import Square


def distance_ft(a: Square, b: Square) -> int:
    """Distance in feet, 5-10-5: each diagonal step of the Chebyshev path costs
    5, then 10, alternating; straight steps cost 5."""
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    diagonals = min(dx, dy)
    straight = max(dx, dy) - diagonals
    total = 0
    for index in range(diagonals):
        total += 5 if index % 2 == 0 else 10
    return total + 5 * straight
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/space/geometry.py tests/domain/test_geometry.py
git commit -m "feat(domain): add 5-10-5 grid distance"
```

---

### Task 3: Line of sight — corner-to-corner with the corner-graze rule

**Files:**
- Modify: `src/domain/space/geometry.py` (append)
- Test: `tests/domain/test_geometry.py` (append)

**Interfaces:**
- Consumes: `Square`, `Board`, `board.is_wall` (Task 1); `distance_ft` (Task 2).
- Produces: `line_of_sight(board: Board, a: Square, b: Square) -> bool`; internal `_corners(square) -> tuple[tuple[float, float], ...]` and `_blocked_segment_count(board, a, b) -> int`, which Task 4's `cover_between` reuses.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_geometry.py`:

```python
from domain.space.board import Board
from domain.space.geometry import line_of_sight


def _board(walls: set[tuple[int, int]]) -> Board:
    return Board(
        width=6,
        height=6,
        walls=frozenset(Square(x, y) for x, y in walls),
    )


def test_open_room_has_line_of_sight() -> None:
    assert line_of_sight(_board(set()), Square(0, 0), Square(5, 5))


def test_wall_in_the_same_row_blocks_sight() -> None:
    assert not line_of_sight(_board({(2, 0)}), Square(0, 0), Square(4, 0))


def test_peeking_past_a_wall_corner_sees_the_target() -> None:
    # Attacker (0,0), target (2,2), wall (1,1): the segment (1,0)->(3,2) touches
    # the wall only at its corner (2,1), so sight exists.
    assert line_of_sight(_board({(1, 1)}), Square(0, 0), Square(2, 2))


def test_line_grazing_only_a_wall_corner_is_clear() -> None:
    assert line_of_sight(_board({(1, 1)}), Square(0, 0), Square(1, 2))


def test_solid_wall_block_between_diagonals_blocks_sight() -> None:
    walls = {(1, 1), (1, 2), (2, 1), (2, 2)}
    assert not line_of_sight(_board(walls), Square(0, 0), Square(3, 3))


def test_a_wall_nowhere_near_the_line_does_not_block() -> None:
    assert line_of_sight(_board({(4, 4)}), Square(0, 0), Square(1, 1))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py -q`
Expected: FAIL — `ImportError: cannot import name 'line_of_sight'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/domain/space/geometry.py`:

```python
_Point = tuple[float, float]

_CORNER_OFFSETS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 1.0),
)


def _corners(square: Square) -> tuple[_Point, ...]:
    return tuple((square.x + dx, square.y + dy) for dx, dy in _CORNER_OFFSETS)


def _cell_blocks(cell: Square, p1: _Point, p2: _Point) -> bool:
    """Liang-Barsky clip of the segment against the cell's closed area.

    The wall blocks unless the segment meets the cell only at one of the cell's
    four corner points (R1 spec §3 edge rule): a positive-length overlap blocks,
    a single contact point blocks unless it is exactly a corner.
    """
    x, y = cell.x, cell.y
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for delta, origin, low, high in ((dx, p1[0], x, x + 1), (dy, p1[1], y, y + 1)):
        if delta == 0:
            if not low <= origin <= high:
                return False
            continue
        enter = (low - origin) / delta
        exit_ = (high - origin) / delta
        if delta > 0:
            if enter > t1 or exit_ < t0:
                return False
            t0, t1 = max(t0, enter), min(t1, exit_)
        else:
            if exit_ > t1 or enter < t0:
                return False
            t0, t1 = max(t0, exit_), min(t1, enter)
    if t0 > t1:
        return False
    if t0 == t1:
        point = (p1[0] + t0 * dx, p1[1] + t0 * dy)
        corner_set = {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}
        return not any(point == corner for corner in corner_set)
    return True


def _blocked_segment_count(board: Board, a: Square, b: Square) -> int:
    blocked = 0
    for p1 in _corners(a):
        for p2 in _corners(b):
            if any(_cell_blocks(wall, p1, p2) for wall in board.walls):
                blocked += 1
    return blocked


def line_of_sight(board: Board, a: Square, b: Square) -> bool:
    """Sight exists if at least one corner-to-corner segment touches no wall."""
    return _blocked_segment_count(board, a, b) < len(_CORNER_OFFSETS) ** 2
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py -q`
Expected: 14 passed (8 from Task 2 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add src/domain/space/geometry.py tests/domain/test_geometry.py
git commit -m "feat(domain): add corner-to-corner line of sight"
```

---

### Task 4: Cover between two squares

**Files:**
- Modify: `src/domain/space/geometry.py` (append)
- Test: `tests/domain/test_geometry.py` (append)

**Interfaces:**
- Consumes: `_blocked_segment_count`, `line_of_sight` (Task 3); `Board`, `CoverLevel`, `higher_cover` (Task 1).
- Produces: `cover_between(board: Board, a: Square, b: Square) -> CoverLevel` — Task 6's validate step consumes this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_geometry.py`:

```python
from domain.space.geometry import cover_between


def test_no_walls_no_flag_means_no_cover() -> None:
    assert cover_between(_board(set()), Square(0, 0), Square(4, 0)) is CoverLevel.NONE


def test_target_squares_own_cover_flag_applies() -> None:
    board = Board(width=6, height=6, cover={Square(4, 0): CoverLevel.HALF})
    assert cover_between(board, Square(0, 0), Square(4, 0)) is CoverLevel.HALF
    board = Board(width=6, height=6, cover={Square(4, 0): CoverLevel.THREE_QUARTERS})
    assert cover_between(board, Square(0, 0), Square(4, 0)) is (
        CoverLevel.THREE_QUARTERS
    )


def test_partial_obstruction_grants_half_cover() -> None:
    # The peeking case from Task 3: 15 of 16 segments blocked.
    assert cover_between(_board({(1, 1)}), Square(0, 0), Square(2, 2)) is (
        CoverLevel.HALF
    )


def test_fully_blocked_lines_mean_total_cover() -> None:
    assert cover_between(_board({(2, 0)}), Square(0, 0), Square(4, 0)) is (
        CoverLevel.TOTAL
    )


def test_partial_obstruction_upgrades_to_the_targets_flag() -> None:
    board = Board(
        width=6,
        height=6,
        walls=frozenset({Square(1, 1)}),
        cover={Square(2, 2): CoverLevel.THREE_QUARTERS},
    )
    assert cover_between(board, Square(0, 0), Square(2, 2)) is (
        CoverLevel.THREE_QUARTERS
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py -q`
Expected: FAIL — `ImportError: cannot import name 'cover_between'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/domain/space/geometry.py`:

```python
def cover_between(board: Board, a: Square, b: Square) -> CoverLevel:
    """Cover the target has against an attacker at ``a`` (R1 spec §3).

    All 16 segments blocked -> TOTAL; none blocked -> the target square's own
    flag; some blocked -> at least HALF, upgraded to the target's flag.
    """
    blocked = _blocked_segment_count(board, a, b)
    own = board.cover_at(b)
    if blocked >= len(_CORNER_OFFSETS) ** 2:
        return CoverLevel.TOTAL
    if blocked == 0:
        return own
    return higher_cover(CoverLevel.HALF, own)
```

Add the import at the top of the file, alongside the existing ones:

```python
from domain.space.board import Board, CoverLevel, higher_cover
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_geometry.py -q`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/space/geometry.py tests/domain/test_geometry.py
git commit -m "feat(domain): add cover between squares"
```

---

### Task 5: Combat carries a board and positions; spawns assigned at start

**Files:**
- Modify: `src/domain/combat/state.py:56-65` (Combat fields)
- Modify: `src/domain/combat/engine.py:39-62` (start signature, position assignment)
- Modify: `src/domain/space/board.py` (add `Spawns`)
- Test: `tests/domain/test_combat.py` (extend; the `_start` helper at line 86 gains two optional parameters)

**Interfaces:**
- Consumes: `Square`, `Board` (Task 1).
- Produces: `Spawns(party: tuple[Square, ...], enemies: tuple[Square, ...])` in `domain.space.board`; `CombatEngine.start(game, participant_ids, collector, board=None, spawns=None) -> Combat`; `Combat.board: Board | None`; `Combat.positions: dict[CharacterId, Square]`. Task 6 consumes all three; Task 8's loader produces `Spawns`.

- [ ] **Step 1: Write the failing tests**

Extend the `_start` helper in `tests/domain/test_combat.py` (line 86) with two optional parameters passed through to `engine.start`:

```python
def _start(
    dice: DiceRoller,
    game: Game,
    board: Board | None = None,
    spawns: Spawns | None = None,
) -> tuple[CombatEngine, Combat, EventCollector]:
    engine = CombatEngine(dice)
    collector = EventCollector(game_id=game.game_id)
    combat = engine.start(
        game, (*game.party_ids, *game.enemy_ids), collector, board=board, spawns=spawns
    )
```

(keep the helper's existing return statement). Then append these tests:

```python
from domain.space.board import Board, CoverLevel, Spawns
from domain.space.square import Square


def _spawns() -> Spawns:
    return Spawns(
        party=(Square(0, 0), Square(0, 1), Square(0, 2)),
        enemies=(Square(4, 0), Square(4, 1), Square(4, 2)),
    )


def _board() -> Board:
    return Board(width=5, height=5)


def test_start_places_participants_on_spawn_squares_in_list_order() -> None:
    game = _game(_fighter(), _goblin())
    _, combat, _ = _start(DiceRoller(seed=1), game, board=_board(), spawns=_spawns())
    assert combat.positions[game.party_ids[0]] == Square(0, 0)
    assert combat.positions[game.enemy_ids[0]] == Square(4, 0)


def test_start_without_a_board_leaves_positions_empty() -> None:
    game = _game(_fighter(), _goblin())
    _, combat, _ = _start(DiceRoller(seed=1), game)
    assert combat.positions == {}
    assert combat.board is None


def test_more_participants_than_spawns_is_rejected() -> None:
    game = _game(_fighter(), _goblin())
    spawns = Spawns(party=(Square(0, 0),), enemies=(Square(4, 0),))
    with pytest.raises(ValidationError):
        _start(DiceRoller(seed=1), game, board=_board(), spawns=spawns)


def test_duplicate_spawn_squares_are_rejected() -> None:
    game = _game(_fighter(), _goblin())
    spawns = Spawns(party=(Square(0, 0),), enemies=(Square(0, 0),))
    with pytest.raises(ValidationError):
        _start(DiceRoller(seed=1), game, board=_board(), spawns=spawns)


def test_spawn_on_a_wall_is_rejected() -> None:
    game = _game(_fighter(), _goblin())
    board = Board(width=5, height=5, walls=frozenset({Square(4, 0)}))
    with pytest.raises(ValidationError):
        _start(DiceRoller(seed=1), game, board=board, spawns=_spawns())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_combat.py -q`
Expected: FAIL — `ImportError: cannot import name 'Spawns' from 'domain.space.board'`.

- [ ] **Step 3: Write the minimal implementation**

Add `Spawns` to `src/domain/space/board.py`:

```python
@dataclass(frozen=True)
class Spawns:
    party: tuple[Square, ...]
    enemies: tuple[Square, ...]
```

Add the two fields to `Combat` in `src/domain/combat/state.py` (after `status`), with imports `from dataclasses import dataclass, field` and `from domain.space.board import Board` / `from domain.space.square import Square`:

```python
    board: Board | None = None
    positions: dict[CharacterId, Square] = field(default_factory=dict)
```

In `src/domain/combat/engine.py`, extend `start` and add the assignment helper; add `from domain.common.errors import ValidationError` and the space imports:

```python
    def start(
        self,
        game: Game,
        participant_ids: Sequence[CharacterId],
        collector: EventCollector,
        board: Board | None = None,
        spawns: Spawns | None = None,
    ) -> Combat:
        entries = roll_initiative(self._dice, game.characters, participant_ids)
        for entry in entries:
            collector.record(
                InitiativeRolled(character_id=entry.character_id, total=entry.total)
            )
        first = entries[0].character_id
        combat = Combat(
            entries=entries,
            economy=ActionEconomy(movement_budget_ft=game.characters[first].speed_ft),
            board=board,
            positions=(
                _assign_positions(game, board, spawns) if board is not None else {}
            ),
        )
```

(keep the two `collector.record` calls that follow unchanged), plus:

```python
def _assign_positions(
    game: Game, board: Board, spawns: Spawns
) -> dict[CharacterId, Square]:
    """Spawn squares are content: assign in list order, reject any gap or clash."""
    if len(game.party_ids) > len(spawns.party) or len(game.enemy_ids) > len(
        spawns.enemies
    ):
        raise ValidationError("not enough spawn squares for every participant")
    positions: dict[CharacterId, Square] = {}
    for character_id, square in zip(game.party_ids, spawns.party, strict=False):
        positions[character_id] = square
    for character_id, square in zip(game.enemy_ids, spawns.enemies, strict=False):
        positions[character_id] = square
    if len(set(positions.values())) != len(positions):
        raise ValidationError("spawn squares must be distinct")
    for square in positions.values():
        if not board.in_bounds(square) or board.is_wall(square):
            raise ValidationError(f"spawn square {square} is not a standing square")
    return positions
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_combat.py -q`
Expected: all pass (existing tests unchanged — no board means no new behaviour).

- [ ] **Step 5: Commit**

```bash
git add src/domain/combat src/domain/space/board.py tests/domain/test_combat.py
git commit -m "feat(domain): combat carries an optional battle board with spawn placement"
```

---

### Task 6: Range, line of sight and cover in attack validation

**Files:**
- Modify: `src/domain/combat/engine.py:64-95` (validate) and `:115-145` (resolve)
- Test: `tests/domain/test_combat.py` (append)

**Interfaces:**
- Consumes: `distance_ft`, `line_of_sight`, `cover_between` (Tasks 2-4); `Combat.board`/`Combat.positions`/`Spawns` (Task 5).
- Produces: reject codes `out_of_range`, `no_line_of_sight`, `total_cover`; effective AC = `armor_class + 2` (HALF) / `+ 5` (THREE_QUARTERS). The Bridge plan and R3+ consume these codes.

- [ ] **Step 1: Write the failing tests**

Extend the `_weapon` helper in `tests/domain/test_combat.py` with `range_ft: int = 5` passed to `Weapon`. Then append:

```python
def _grid(
    walls: set[tuple[int, int]] = frozenset(),
    cover: dict[tuple[int, int], CoverLevel] | None = None,
) -> tuple[Board, Spawns]:
    board = Board(
        width=10,
        height=10,
        walls=frozenset(Square(x, y) for x, y in walls),
        cover={} if cover is None else {
            Square(x, y): level for (x, y), level in cover.items()
        },
    )
    spawns = Spawns(party=(Square(0, 0),), enemies=(Square(4, 0),))
    return board, spawns


def test_attack_beyond_weapon_range_is_rejected() -> None:
    # (0,0) -> (4,0) is 20 ft; a longsword reaches 5 ft.
    seed = _seed_with_rolls([16, 10, 15])
    game = _game(_fighter(), _goblin())
    board, spawns = _grid()
    engine, combat, collector = _start(
        DiceRoller(seed=seed), game, board=board, spawns=spawns
    )
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    result = engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    assert result.valid is False
    assert result.error_code == "out_of_range"
    assert combat.economy.action_taken is False, "a rejected attack consumes nothing"
    assert not [e for e in collector.events if e.event_type == "damage_applied"]


def test_attack_without_line_of_sight_is_rejected() -> None:
    # (0,0) -> (2,0) is 10 ft, inside a pike's reach, but a wall stands between.
    seed = _seed_with_rolls([16, 10, 15])
    game = _game(_fighter(), _goblin())
    game.characters[game.party_ids[0]].equipped_weapon = _weapon(
        "pike", "Pike", 8, range_ft=10
    )
    board, spawns = _grid(walls={(1, 0)})
    spawns = Spawns(party=(Square(0, 0),), enemies=(Square(2, 0),))
    engine, combat, collector = _start(
        DiceRoller(seed=seed), game, board=board, spawns=spawns
    )
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    result = engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    assert result.valid is False
    assert result.error_code == "no_line_of_sight"


def test_total_cover_cannot_be_targeted() -> None:
    seed = _seed_with_rolls([16, 10, 20])
    game = _game(_fighter(), _goblin())
    game.characters[game.party_ids[0]].equipped_weapon = _weapon(
        "spear", "Spear", 8, range_ft=20
    )
    board, spawns = _grid(cover={(4, 0): CoverLevel.TOTAL})
    engine, combat, collector = _start(
        DiceRoller(seed=seed), game, board=board, spawns=spawns
    )
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    result = engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    assert result.valid is False
    assert result.error_code == "total_cover"


def test_half_cover_flips_a_hit_into_a_miss() -> None:
    # Fighter's attack bonus is +5; goblin AC 13. A natural 9 (total 14) hits 13
    # but misses the covered 15 — the same seed must flip on the board alone.
    seed = _seed_with_rolls([16, 10, 9])
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]
    proposal = AttackProposal(actor_id=actor_id, target_id=target_id)
    bare = engine.resolve(game, combat, proposal, EventCollector(game_id=game.game_id))
    assert bare.valid is True

    board, spawns = _grid(cover={(4, 0): CoverLevel.HALF})
    game2 = _game(_fighter(), _goblin())
    engine2, combat2, collector2 = _start(
        DiceRoller(seed=seed), game2, board=board, spawns=spawns
    )
    actor2 = combat2.active_actor()
    target2 = game2.opponents_of(actor2)[0]
    covered = engine2.resolve(
        game2,
        combat2,
        AttackProposal(actor_id=actor2, target_id=target2),
        collector2,
    )

    assert covered.valid is True, "cover is not a rejection"
    resolved = [e for e in collector2.events if e.event_type == "attack_resolved"]
    assert resolved[-1].payload["hit"] is False
    assert resolved[-1].payload["target_ac"] == 15
    assert not [e for e in collector2.events if e.event_type == "damage_applied"]


def test_combat_without_a_board_rejects_nothing_new() -> None:
    seed = _seed_with_rolls([16, 10, 15])
    game = _game(_fighter(), _goblin())
    engine, combat, collector = _start(DiceRoller(seed=seed), game)
    actor_id = combat.active_actor()
    target_id = game.opponents_of(actor_id)[0]

    result = engine.resolve(
        game, combat, AttackProposal(actor_id=actor_id, target_id=target_id), collector
    )

    assert result.valid is True
    assert result.error_code == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_combat.py -q`
Expected: the five new tests FAIL (`out_of_range` etc. never returned); all existing tests still pass.

- [ ] **Step 3: Write the minimal implementation**

In `src/domain/combat/engine.py`, add imports:

```python
from domain.space.board import Board, CoverLevel, Spawns
from domain.space.geometry import cover_between, distance_ft, line_of_sight
```

Extend `validate` — after the target/side checks and before `return ValidationResult.ok()`:

```python
        board = combat.board
        if board is None:
            return ValidationResult.ok()
        actor_square = combat.positions[actor.id]
        target_square = combat.positions[target.id]
        if distance_ft(actor_square, target_square) > weapon.range_ft:
            return ValidationResult.reject("target is out of range", "out_of_range")
        if not line_of_sight(board, actor_square, target_square):
            return ValidationResult.reject(
                "no line of sight to target", "no_line_of_sight"
            )
        if cover_between(board, actor_square, target_square) is CoverLevel.TOTAL:
            return ValidationResult.reject("target has total cover", "total_cover")
        return ValidationResult.ok()
```

In `resolve`, replace the bare `target.armor_class` argument to `attack_roll` with an effective AC:

```python
        target_ac = target.armor_class
        if combat.board is not None:
            cover = cover_between(
                combat.board,
                combat.positions[actor.id],
                combat.positions[target.id],
            )
            if cover is CoverLevel.HALF:
                target_ac += 2
            elif cover is CoverLevel.THREE_QUARTERS:
                target_ac += 5
        roll = self._checks.attack_roll(attack_bonus, target_ac)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/domain/test_combat.py -q`
Expected: all pass, including every pre-existing test unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/domain/combat/engine.py tests/domain/test_combat.py
git commit -m "feat(domain): validate range, line of sight and cover on attacks"
```

---

### Task 7: Battle map in the views and the CLI renderer

**Files:**
- Modify: `src/application/views.py:30-36` (CombatView + new BattleMapView)
- Modify: `src/application/game_service.py:366-381` (get_view builds the map view)
- Modify: `src/interfaces/cli/renderer.py` (render_game_view draws the map)
- Test: `tests/interfaces/test_renderer.py` (append)

**Interfaces:**
- Consumes: `Combat.board`, `Combat.positions` (Task 5).
- Produces: `BattleMapView(width: int, height: int, walls: tuple[tuple[int, int], ...], positions: dict[str, tuple[int, int]])` and `CombatView.map: BattleMapView | None`. The API DTO layer and the Bridge may consume this later; nothing in `ai/` changes in R1.

- [ ] **Step 1: Write the failing test**

Append to `tests/interfaces/test_renderer.py`:

```python
from application.views import BattleMapView


def test_battle_map_renders_walls_and_occupants() -> None:
    console, buffer = _console()
    view = GameView(
        game_id="game-1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[
            CharacterView(
                id="c1",
                name="Arin",
                character_class="fighter",
                level=1,
                hp_current=12,
                hp_max=12,
                armor_class=16,
                conditions=[],
                is_defeated=False,
            )
        ],
        enemies=[
            CharacterView(
                id="c2",
                name="Goblin",
                character_class=None,
                level=1,
                hp_current=7,
                hp_max=7,
                armor_class=13,
                conditions=[],
                is_defeated=False,
            )
        ],
        combat=CombatView(
            round_number=1,
            status="active",
            active_actor_id="c1",
            initiative_order=[],
            map=BattleMapView(
                width=3,
                height=2,
                walls=((1, 0),),
                positions={"c1": (0, 0), "c2": (2, 1)},
            ),
        ),
    )

    render_game_view(console, view)

    out = buffer.getvalue()
    assert "#" in out, "the wall must render"
    assert "@" in out, "the party member must render"
    assert "G" in out, "the enemy renders as the first letter of its name"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/interfaces/test_renderer.py -q`
Expected: FAIL — `ImportError: cannot import name 'BattleMapView'`.

- [ ] **Step 3: Write the minimal implementation**

In `src/application/views.py`, add above `CombatView`:

```python
@dataclass(frozen=True)
class BattleMapView:
    width: int
    height: int
    walls: tuple[tuple[int, int], ...]
    positions: dict[str, tuple[int, int]]
```

and give `CombatView` one more field with a default: `map: BattleMapView | None = None`.

In `src/application/game_service.py`, inside `get_view`'s `CombatView(...)` construction, add the `map` argument:

```python
                map=(
                    BattleMapView(
                        width=combat.board.width,
                        height=combat.board.height,
                        walls=tuple(
                            (square.x, square.y)
                            for square in sorted(combat.board.walls)
                        ),
                        positions={
                            str(character_id): (square.x, square.y)
                            for character_id, square in combat.positions.items()
                        },
                    )
                    if combat.board is not None
                    else None
                ),
```

(import `BattleMapView` from `application.views`).

In `src/interfaces/cli/renderer.py`, call `_render_battle_map(console, view, combat)` immediately after the initiative line in `render_game_view`, and add:

```python
def _render_battle_map(console: Console, view: GameView, combat: CombatView) -> None:
    board = combat.map
    if board is None:
        return
    party_ids = {member.id for member in view.party}
    enemy_initials = {
        member.id: (member.name[:1] or "?").upper() for member in view.enemies
    }
    for y in reversed(range(board.height)):
        row = ""
        for x in range(board.width):
            occupant = next(
                (cid for cid, sq in board.positions.items() if sq == (x, y)), None
            )
            if (x, y) in board.walls:
                row += "#"
            elif occupant is not None and occupant in party_ids:
                row += "@"
            elif occupant is not None:
                row += enemy_initials.get(occupant, "?")
            else:
                row += "."
        console.print(row)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/interfaces/test_renderer.py tests/interfaces/test_cli.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/application/views.py src/application/game_service.py src/interfaces/cli/renderer.py tests/interfaces/test_renderer.py
git commit -m "feat(interfaces): render the battle map in the combat view"
```

---

### Task 8: The map loader, the encounter wiring, and the shipped map

**Files:**
- Create: `config/maps/eastern_tower.toml`
- Modify: `config/encounter.toml` (add `map = "eastern_tower"` under the header comment)
- Modify: `src/application/world_catalog.py` (append `BattleMap`, `InvalidMapConfigError`, `load_battle_map`)
- Modify: `src/application/encounter.py` (append `encounter_map_name`)
- Modify: `src/application/game_service.py:57-73` (constructor) and `:200-208` (`_open_combat`)
- Modify: `src/session/factory.py:87-112` (`build_service`) and `:322-331` (`build_session`)
- Test: `tests/application/test_world_catalog.py` (append), `tests/application/test_game_service.py` (append)

**Interfaces:**
- Consumes: `Board`, `Spawns`, `Square`, `CoverLevel` (Tasks 1, 5); `CombatEngine.start(board=, spawns=)` (Task 5).
- Produces: `BattleMap(board: Board, spawns: Spawns)`; `load_battle_map(path: Path) -> BattleMap` raising `InvalidMapConfigError` on any malformed file; `encounter_map_name(path: str | Path) -> str | None`; `GameService(..., battle_map: BattleMap | None = None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/application/test_world_catalog.py`:

```python
import pytest

from application.world_catalog import InvalidMapConfigError, load_battle_map
from domain.common.errors import ValidationError
from domain.space.board import CoverLevel
from domain.space.square import Square

VALID_MAP = """\
[map]
name = "Test Room"
width = 5
height = 5
walls = [[0, 0]]

[[cover]]
square = [2, 2]
level = "half"

[spawns.party]
squares = [[1, 1]]

[spawns.enemies]
squares = [[4, 4]]
"""


def _write_map(tmp_path, text: str):
    path = tmp_path / "map.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_battle_map_parses_board_cover_and_spawns(tmp_path) -> None:
    battle_map = load_battle_map(_write_map(tmp_path, VALID_MAP))
    assert battle_map.board.width == 5
    assert battle_map.board.is_wall(Square(0, 0))
    assert battle_map.board.cover_at(Square(2, 2)) is CoverLevel.HALF
    assert battle_map.spawns.party == (Square(1, 1),)
    assert battle_map.spawns.enemies == (Square(4, 4),)


@pytest.mark.parametrize(
    "text",
    [
        '[map]\nwidth = 5\nheight = 5\n[spawns.party]\nsquares = [[1,1]]\n',  # no spawns.enemies
        '[map]\nwidth = 5\nheight = 5\nwalls = [[9, 9]]\n[spawns.party]\nsquares = [[1,1]]\n[spawns.enemies]\nsquares = [[4,4]]\n',  # wall out of bounds
        '[map]\nwidth = 5\nheight = 5\n[[cover]]\nsquare = [1,1]\nlevel = "murk"\n[spawns.party]\nsquares = [[1,1]]\n[spawns.enemies]\nsquares = [[4,4]]\n',  # unknown level
        '[map]\nwidth = 5\nheight = 5\n[[cover]]\nsquare = [1,1]\nlevel = "half"\n[[cover]]\nsquare = [1,1]\nlevel = "half"\n[spawns.party]\nsquares = [[1,1]]\n[spawns.enemies]\nsquares = [[4,4]]\n',  # duplicate cover
        'width = 5\nheight = 5\n',  # no [map] table
    ],
)
def test_malformed_maps_fail_loudly_at_load(tmp_path, text: str) -> None:
    with pytest.raises((InvalidMapConfigError, ValidationError)):
        load_battle_map(_write_map(tmp_path, text))
```

Append to `tests/application/test_game_service.py` (if the file has no enemy command helper, add `_goblin_command()` mirroring `_fighter_command()` with `character_type="enemy"`, `armor_class=13`, `max_hp=7`, and the scimitar `WeaponSpec`):

```python
from application.world_catalog import BattleMap
from domain.space.board import Board, Spawns
from domain.space.square import Square


def _battle_map() -> BattleMap:
    return BattleMap(
        board=Board(width=10, height=10),
        spawns=Spawns(party=(Square(0, 0),), enemies=(Square(4, 0),)),
    )


def test_start_combat_places_combatants_on_the_encounter_map() -> None:
    event_store = InMemoryEventRepository()
    service = GameService(
        InMemoryGameRepository(event_store), event_store, battle_map=_battle_map()
    )
    game_id = service.create_game(CreateGameCommand(seed=1))
    service.add_character(game_id, _fighter_command())
    service.add_character(game_id, _goblin_command())

    view = service.start_combat(game_id)

    assert view.combat is not None
    assert view.combat.map is not None
    assert view.combat.map.positions, "combatants must start on spawn squares"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/test_world_catalog.py tests/application/test_game_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'InvalidMapConfigError'` / unexpected keyword `battle_map`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/application/world_catalog.py` (imports: `from dataclasses import dataclass`, `from domain.space.board import Board, CoverLevel, Spawns`, `from domain.space.square import Square`):

```python
@dataclass(frozen=True)
class BattleMap:
    board: Board
    spawns: Spawns


class InvalidMapConfigError(ValueError):
    pass


def _map_int(table: dict[str, object], key: str, where: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or value < 1:
        raise InvalidMapConfigError(f"{where} needs a positive integer '{key}'")
    return value


def _map_square(value: object, where: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or not all(
        isinstance(item, int) for item in value
    ):
        raise InvalidMapConfigError(f"{where} needs a [x, y] square, got {value!r}")
    return (value[0], value[1])


def _map_squares(value: object, where: str) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise InvalidMapConfigError(f"{where} needs a list of [x, y] squares")
    return [_map_square(entry, where) for entry in value]


def load_battle_map(path: Path) -> BattleMap:
    """toml -> BattleMap; every malformation fails loudly here, never mid-combat."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    table = data.get("map")
    if not isinstance(table, dict):
        raise InvalidMapConfigError(f"{path.name} needs a [map] table")
    width = _map_int(table, "width", path.name)
    height = _map_int(table, "height", path.name)
    walls = frozenset(
        Square(x, y) for x, y in _map_squares(table.get("walls", []), path.name)
    )
    cover: dict[Square, CoverLevel] = {}
    for entry in data.get("cover", []):
        if not isinstance(entry, dict):
            raise InvalidMapConfigError(f"{path.name}: each [[cover]] must be a table")
        x, y = _map_square(entry.get("square"), path.name)
        try:
            level = CoverLevel(str(entry.get("level")))
        except ValueError as error:
            raise InvalidMapConfigError(
                f"{path.name}: unknown cover level {entry.get('level')!r}"
            ) from error
        if Square(x, y) in cover:
            raise InvalidMapConfigError(f"{path.name}: duplicate cover square ({x}, {y})")
        cover[Square(x, y)] = level
    spawns_table = data.get("spawns")
    if not isinstance(spawns_table, dict):
        raise InvalidMapConfigError(f"{path.name} needs a [spawns] table")
    party_table = spawns_table.get("party")
    enemies_table = spawns_table.get("enemies")
    if not isinstance(party_table, dict) or not isinstance(enemies_table, dict):
        raise InvalidMapConfigError(f"{path.name}: [spawns] needs party and enemies")
    try:
        board = Board(width=width, height=height, walls=walls, cover=cover)
    except ValidationError as error:
        raise InvalidMapConfigError(f"{path.name}: {error}") from error
    return BattleMap(
        board=board,
        spawns=Spawns(
            party=tuple(
                Square(x, y)
                for x, y in _map_squares(party_table.get("squares", []), path.name)
            ),
            enemies=tuple(
                Square(x, y)
                for x, y in _map_squares(enemies_table.get("squares", []), path.name)
            ),
        ),
    )
```

(`ValidationError` is already imported by this module's neighbours; add `from domain.common.errors import ValidationError` if absent.)

Append to `src/application/encounter.py` (add `import tomllib` and `from pathlib import Path` if absent):

```python
def encounter_map_name(path: str | Path) -> str | None:
    """The encounter's battle-map name, or None when the encounter is ungridded."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    value = data.get("map")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise EncounterError("encounter 'map' must be a non-empty string")
    return value
```

In `src/application/game_service.py`: `__init__` gains `battle_map: BattleMap | None = None` and stores `self._battle_map = battle_map` (import `from application.world_catalog import BattleMap`); `_open_combat` passes them to the engine:

```python
        board = self._battle_map.board if self._battle_map is not None else None
        spawns = self._battle_map.spawns if self._battle_map is not None else None
        combat = engine.start(
            game,
            (*game.party_ids, *game.enemy_ids),
            collector,
            board=board,
            spawns=spawns,
        )
```

In `src/session/factory.py`: `build_service` gains `battle_map: BattleMap | None = None` and passes `battle_map=battle_map` in both branches; `build_session` loads it after the world:

```python
    map_name = encounter_map_name(CONFIG_DIR / "encounter.toml")
    battle_map = (
        load_battle_map(CONFIG_DIR / "maps" / f"{map_name}.toml") if map_name else None
    )
    service = build_service(config.db, world=world, battle_map=battle_map)
```

Create `config/maps/eastern_tower.toml`:

```toml
[map]
name = "Eastern Tower"
width = 10
height = 10

walls = [[4, 0], [5, 0], [6, 0], [0, 5], [9, 5]]

[[cover]]
square = [3, 4]
level = "half"

[[cover]]
square = [6, 4]
level = "three_quarters"

[spawns.party]
squares = [[1, 1], [2, 1], [1, 2], [2, 2]]

[spawns.enemies]
squares = [[8, 8], [7, 8], [8, 7]]
```

Add to `config/encounter.toml`, directly under its header comment:

```toml
map = "eastern_tower"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application tests/session tests/integration -q`
Expected: all pass; the shipped session now opens combat on the tower map.

- [ ] **Step 5: Commit**

```bash
git add config src/application src/session tests/application
git commit -m "feat(application): load the encounter battle map and grid combat"
```

---

### Task 9: Full gate and the roadmap row

**Files:**
- Modify: `docs/superpowers/plans/README.md` (row 13 `In progress` -> `Complete`; row 14 `Planned` -> `Complete`)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Run the full gate**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
```

Expected: full suite green (605 prior + all R1 tests), ruff clean, mypy clean.

- [ ] **Step 2: Update the roadmap rows**

In `docs/superpowers/plans/README.md`, set row 13's Status to `Complete` and row 14's Status to `Complete`. The consistency tests do not pin these statuses, so no test changes.

- [ ] **Step 3: Run the consistency suite to confirm nothing drifted**

Run: `.venv/bin/python -m pytest tests/docs -q`
Expected: 17 passed.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/README.md
git commit -m "docs(plans): mark R1 grid and space complete"
```

---
