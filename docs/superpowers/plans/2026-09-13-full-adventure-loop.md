# Full-Adventure Loop (Phase 21, CLI-First) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move beyond "kill one goblin in one scene" — a world of data-driven locations with per-character travel, scene-scoped NPC talk, scene-tagged agent memory, and an out-of-combat scene loop that gives agents autonomy between human inputs — validated first through the CLI adapter.

**Architecture:** New domain types (`Location`, `WorldMap`, `TravelService`) under `domain/world/`; per-character placement stored on `Game` and persisted inside the existing JSONB `state` document; an application `WorldCatalog` loads the graph from `config/world.toml`; a `SceneService` drives one agent scene-action per tick (pauses for combat and human turns); the GM's talk path gains scene scoping; episodic memories are tagged with `location_id`. Everything stays LLM-proposes/rules-decides: travel exits, arrival, and combat triggers are all deterministic.

**Tech Stack:** Python 3.12 stdlib (dataclasses, enum, tomllib, sqlite-style in-memory repos unchanged). psycopg/pgserver already present; one additive SQL migration for the memory tag. No new dependencies (CLAUDE.md §55).

**Spec:** No separate spec doc — Design Decisions below were fixed in a grilling session
(2026-09-13) and travel with this plan. Sources of truth remain CLAUDE.md (priority #3),
the Implementation Plan doc (§ Phases 21–22 candidates), and the existing contract doc
`docs/architecture/domain-model-and-api.md` (must NOT change in this plan — web exposure is Phase 22).

## Global Constraints

- LLMs propose; domain decides; engine executes; events record (CLAUDE.md §1). No game rule may rely on LLM output.
- Domain layer imports nothing from application/ai/infrastructure/interfaces (CLAUDE.md §5).
- No new runtime dependencies; stdlib only for the domain/world additions.
- Reproducibility: absent a seed override, placements and travel are deterministic; LLM scene decisions still go through `AgentRuntime.decide_structured` with retry + deterministic fallback.
- The frozen `/api/v1` contract is unchanged; **all** endpoints, DTOs, and UI JS stay untouched (Phase 22 scope).
- Offline suite must pass with no API keys set; live-model work is manually gated.
- Conventional commits scoped by layer: `feat(domain): ...`, `feat(application): ...`, `feat(cli): ...`, `test(...)`.

## Design Decisions (grilling, 2026-09-13)

| # | Question | Decision |
|---|----------|----------|
| 1 | Phase 21 slice | Scenes + NPC talk now; quests → later plan |
| 2 | Scene model | Data-driven locations with exits; GM/agents propose travel, engine validates |
| 3 | Background loop | Fixed-interval tick concept; CLI-first this plan; pause when combat is on a human turn or the scene awaits a human turn |
| 4 | Travel model | Per-character travel proposals, validated against the world graph; arrival is per-character |
| 5 | NPC talk | Extend the existing `say` path (GM director), scene-scoped context |
| 6 | API freeze | Deferred — CLI-first; web exposure is Phase 22, gated on this plan's recorded live CLI smoke |
| 7 | Memory scoping | Episodic memories tagged `location_id`; retrieval keeps current-scene episodic + all semantic |
| 8 | Completion gate | Both: deterministic FakeModelGateway integration test **and** one recorded live-GLM CLI smoke |
| 9 | Tick pacing | Fully configurable (`config/game.toml [loop]`), not hardcoded (§48) |

## File Structure

| File | Responsibility |
|------|----------------|
| `src/domain/world/locations.py` (new) | `LocationExit`, `Location`, `WorldMap` — pure value objects |
| `src/domain/world/travel.py` (new) | `TravelProposal`, `TravelResolution`, `TravelService` — deterministic travel validation + `CharacterArrived` events |
| `src/domain/world/game.py` (modify) | `Game.placements` + placement methods |
| `src/domain/events/events.py` (modify) | `CharacterArrived` event |
| `src/application/world_catalog.py` (new) | toml → `WorldMap` loader (`load_world_catalog(path)`) |
| `src/application/commands.py` (modify) | `TravelCommand` |
| `src/application/game_service.py` (modify) | `travel()`, auto-combat on hostile arrival, scene-aware `GameView` |
| `src/application/views.py` (modify) | `SceneView`; `GameView.scene`; `CharacterView.location_id` |
| `src/infrastructure/persistence/postgres/mapping.py` (modify) | placements in the `state` document |
| `src/application/memory/memory_service.py`, `src/ai/memory/types.py`, `src/ai/memory/` repos (modify) | `MemoryRecord.location_id` tag + filtered retrieval |
| `src/infrastructure/persistence/postgres/migrations/004_agent_memory_locations.sql` (new) | additive `location_id` column |
| `src/application/agents/scene_decisions.py` (new) | `SceneDecision` + schema for LLM out-of-combat decisions |
| `src/application/scene/scene_service.py` (new) | one-agent-per-tick scene loop driver |
| `src/application/gm/director.py` (modify) | scene-scoped context for `say` |
| `src/session/play.py`, `src/session/factory.py`, `src/interfaces/cli/app.py`, `renderer.py` (modify) | `go <exit>` verb, world wiring, scene rendering, tick pacing |
| `config/world.toml`, `config/game.toml` (new) | location graph + loop tuning |
| Tests mirror the tree under `tests/` |

---

### Task 1: Domain locations value objects

**Files:**
- Create: `src/domain/world/locations.py`
- Test: `tests/domain/test_locations.py`

**Interfaces:**
- Consumes: `LocationId` (`src/domain/common/ids.py:44`).
- Produces: `LocationExit(direction: str, destination: LocationId)`, `Location(id: LocationId, name: str, description: str, exits: tuple[LocationExit, ...])` with `.exit(direction) -> LocationExit | None` (case-insensitive match on `direction`), `.is_exit_to(direction) -> LocationId | None`; `WorldMap(locations: dict[LocationId, Location], start_id: LocationId)` with `.get(location_id) -> Location` (raises `KeyError`), `.by_name(name) -> Location | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/test_locations.py
import pytest

from domain.common.ids import LocationId
from domain.world.locations import Location, LocationExit, WorldMap


def _world() -> WorldMap:
    courtyard = LocationId.generate()
    tower = LocationId.generate()
    locations = {
        courtyard: Location(
            id=courtyard,
            name="Ruined Courtyard",
            description="Broken flagstones under an open sky.",
            exits=(LocationExit(direction="north", destination=tower),),
        ),
        tower: Location(
            id=tower,
            name="Eastern Tower",
            description="A weathered stone tower.",
            exits=(LocationExit(direction="south", destination=courtyard),),
        ),
    }
    return WorldMap(locations=locations, start_id=courtyard)


def test_exit_lookup_is_case_insensitive() -> None:
    world = _world()
    start = world.get(world.start_id)
    assert start.is_exit_to("NORTH") is not None
    assert start.exit("n") is None


def test_unknown_exit_returns_none() -> None:
    world = _world()
    assert world.get(world.start_id).exit("west") is None


def test_by_name_matches_location() -> None:
    world = _world()
    assert world.by_name("eastern tower") is not None
    assert world.by_name("nope") is None


def test_get_unknown_location_raises() -> None:
    with pytest.raises(KeyError):
        _world().get(LocationId.generate())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/domain/test_locations.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.world.locations'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/domain/world/locations.py
"""Data-driven locations: the authoritative world graph (pure domain)."""

from dataclasses import dataclass

from domain.common.ids import LocationId


@dataclass(frozen=True)
class LocationExit:
    direction: str
    destination: LocationId


@dataclass(frozen=True)
class Location:
    id: LocationId
    name: str
    description: str
    exits: tuple[LocationExit, ...]

    def exit(self, direction: str) -> LocationExit | None:
        wanted = direction.casefold()
        for candidate in self.exits:
            if candidate.direction.casefold() == wanted:
                return candidate
        return None

    def is_exit_to(self, direction: str) -> LocationId | None:
        found = self.exit(direction)
        return found.destination if found else None


@dataclass
class WorldMap:
    locations: dict[LocationId, Location]
    start_id: LocationId

    def get(self, location_id: LocationId) -> Location:
        return self.locations[location_id]

    def by_name(self, name: str) -> Location | None:
        wanted = name.casefold()
        for location in self.locations.values():
            if location.name.casefold() == wanted:
                return location
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/domain/test_locations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/world/locations.py tests/domain/test_locations.py
git commit -m "feat(domain): add data-driven location and world-map value objects"
```

---

### Task 2: Game placements + persistence round-trip

**Files:**
- Modify: `src/domain/world/game.py` (Game dataclass, after `enemy_ids`)
- Modify: `src/infrastructure/persistence/postgres/mapping.py` (`game_to_row`, `game_from_row` / `_game_from_row`)
- Modify: `src/infrastructure/persistence/in_memory.py` (keep repository copy semantics)
- Test: `tests/domain/test_game.py` (extend), `tests/infrastructure/test_in_memory_save.py`, `tests/infrastructure/test_postgres_roundtrip.py` (extend existing roundtrip file if named differently — locate with `grep -l game_roundtrip tests/infrastructure`)

**Interfaces:**
- Consumes: `LocationId` (`domain/common/ids.py:44`), `Game` fields as of `src/domain/world/game.py:19-31`.
- Produces: `Game.placements: dict[CharacterId, LocationId]` (default empty), `Game.place(character_id: CharacterId, location_id: LocationId) -> None` (raises `KeyError` for unknown character), `Game.location_of(character_id) -> LocationId | None`, `Game.residents_of(location_id) -> list[CharacterId]` (Party ids then enemy ids, insertion order). Persisted inside the existing `games.state` JSONB document under key `"placements"` (`{character_id: location_id}`) — **no SQL migration needed**; absent key loads as `{}` for backward compatibility.

- [ ] **Step 1: Write the failing domain test** (extend `tests/domain/test_game.py`)

```python
def test_placements_roundtrip_and_residents() -> None:
    game = _game()  # existing helper in this module builds a Game with characters
    first, second = next(iter(game.characters)), list(game.characters)[1]
    location = LocationId.generate()
    game.place(first, location)
    assert game.location_of(first) == location
    assert game.location_of(second) is None
    assert game.residents_of(location) == [first]
    with pytest.raises(KeyError):
        game.place(CharacterId.generate(), location)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/domain/test_game.py -q`
Expected: FAIL — `AttributeError: 'Game' object has no attribute 'place'`

- [ ] **Step 3: Implement on Game** (in `src/domain/world/game.py`)

```python
    placements: dict[CharacterId, LocationId] = field(default_factory=dict)

    def place(self, character_id: CharacterId, location_id: LocationId) -> None:
        self.get_character(character_id)  # raises KeyError for unknown ids
        self.placements[character_id] = location_id

    def location_of(self, character_id: CharacterId) -> LocationId | None:
        return self.placements.get(character_id)

    def residents_of(self, location_id: LocationId) -> list[CharacterId]:
        return [
            cid
            for cid in (*self.party_ids, *self.enemy_ids)
            if cid in self.characters and self.placements.get(cid) == location_id
        ]
```

- [ ] **Step 4: Write the failing persistence round-trip test**

```python
def test_game_roundtrip_preserves_placements(repository, collector) -> None:
    # repository/collector: existing fixtures in this module (InMemoryGameRepository + EventCollector)
    game = _game()  # this module's builder, extended with two party characters in the task
    location = LocationId.generate()
    for cid in game.party_ids:
        game.place(cid, location)
    repository.save(game, collector.drain())
    loaded = repository.get(game.game_id)
    assert loaded.placements == game.placements


def test_game_from_row_defaults_missing_placements() -> None:
    row = {"id": "g", "campaign_id": "c", "campaign_name": "n", "seed": 1,
           "version": 1, "status": "created", "state": {"characters": {}}}
    assert game_from_row(row).placements == {}
```

- [ ] **Step 5: Run to verify FAIL, then implement**

Run: `.venv/bin/pytest tests/infrastructure -q -k placement`
Expected: FAIL — mapping errors / missing key.
Implement in `mapping.py`: in `_game_from_row`, after existing fields:
`placements={CharacterId(cid): LocationId(loc) for cid, loc in (document.get("placements") or {}).items()}` — and in `game_to_row`, add `"placements": {str(cid): str(loc) for cid, loc in game.placements.items()}` to the state document. (JSONB `state` already carries arbitrary keys; the document builder is in `game_to_row` at `mapping.py:124`.)

- [ ] **Step 6: Run the persistence suites**

Run: `.venv/bin/pytest tests/infrastructure tests/domain/test_game.py -q`
Expected: PASS (roundtrip pre-existing test included: `test_game_roundtrip_preserves_every_field` still passes with the new default).

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(domain): per-character location placement on Game with persistence"
```

---

### Task 3: World catalog loader (toml → WorldMap)

**Files:**
- Create: `src/application/world_catalog.py`, `config/world.toml`
- Test: `tests/application/test_world_catalog.py`

**Interfaces:**
- Consumes: `Location`, `WorldMap` from Task 1; stdlib `tomllib`.
- Produces:

```python
class InvalidWorldConfigError(ValueError): ...
def load_world_catalog(path: Path) -> WorldMap
```

`config/world.toml` shape (committed example — written for the live smoke scenario):

```toml
[world]
start = "courtyard"
enemies_at = "eastern_tower"   # where the encounter.toml enemies are placed

[[locations]]
id = "courtyard"
name = "Ruined Courtyard"
description = "Broken flagstones, a dry well, and a path north to an old watchtower."

[[locations.exits]]
direction = "north"
to = "eastern_tower"

[[locations]]
id = "eastern_tower"
name = "Eastern Tower"
description = "A weathered watchtower, its doorway choked with rubble."
```

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_world_catalog.py
import pytest

from application.world_catalog import InvalidWorldConfigError, load_world_catalog


def test_loads_locations_and_start(tmp_path):
    doc = """
[world]
start = "courtyard"

[[locations]]
id = "courtyard"
name = "Ruined Courtyard"
description = "Open ground."

[[locations.exits]]
direction = "north"
to = "eastern_tower"

[[locations]]
id = "eastern_tower"
name = "Eastern Tower"
description = "A tower."
"""
    path = tmp_path / "world.toml"
    path.write_text(doc)
    world = load_world_catalog(path)
    assert world.by_name("ruined courtyard") is not None
    start = world.get(world.start_id)
    assert start.is_exit_to("north") is not None


@pytest.mark.parametrize("missing", [["world"], ["locations"], ["start"]])
def test_missing_sections_raise(tmp_path, missing):
    doc = '\n[world]\nstart = "courtyard"\n' if "start" in missing else ""
    path = tmp_path / "world.toml"
    path.write_text(doc)
    with pytest.raises(InvalidWorldConfigError):
        load_world_catalog(path)
```

- [ ] **Step 2: Verify FAIL** — Run: `.venv/bin/pytest tests/application/test_world_catalog.py -q` — Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# src/application/world_catalog.py
"""Loads the location graph from config/world.toml. Application owns I/O; domain types stay pure."""

import tomllib
from pathlib import Path

from domain.common.ids import LocationId
from domain.world.locations import Location, LocationExit, WorldMap


class InvalidWorldConfigError(ValueError):
    pass


def _require(table: dict[str, object], key: str) -> object:
    if key not in table or not isinstance(table[key], object) or table[key] in (None, ""):
        raise InvalidWorldConfigError(f"world config missing '{key}'")
    return table[key]


def load_world_catalog(path: Path) -> WorldMap:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    world = data.get("world")
    raw_locations = data.get("locations")
    if not isinstance(world, dict) or not isinstance(raw_locations, list) or not raw_locations:
        raise InvalidWorldConfigError("world.toml needs [world].start and [[locations]]")
    locations: dict[LocationId, Location] = {}
    ids: dict[str, LocationId] = {}
    for entry in raw_locations:
        if not isinstance(entry, dict):
            raise InvalidWorldConfigError("each [[locations]] must be a table")
        key = entry.get("id")
        if not isinstance(key, str) or key in ids:
            raise InvalidWorldConfigError(f"bad or duplicate location id: {key!r}")
        ids[key] = LocationId.generate()
    for entry in raw_locations:
        location_id = ids[entry["id"]]
        exits = tuple(
            LocationExit(direction=exit_["direction"], destination=ids[exit_["to"]])
            for exit_ in entry.get("exits", ())
        )
        locations[location_id] = Location(
            id=location_id,
            name=str(entry["name"]),
            description=str(entry["description"]),
            exits=exits,
        )
    start_key = _require(world, "start")
    if start_key not in ids:
        raise InvalidWorldConfigError(f"[world].start '{start_key}' is not a location id")
    return WorldMap(locations=locations, start_id=ids[str(start_key)])
```

- [ ] **Step 4: Verify PASS** — Run: `.venv/bin/pytest tests/application/test_world_catalog.py -q` — Expected: PASS.

- [ ] **Step 5: Create the real `config/world.toml`** with the content shown above.

- [ ] **Step 6: Commit** — `git commit -m "feat(application): world catalog loader with config/world.toml"`

---

### Task 4: Domain travel service + CharacterArrived event

**Files:**
- Modify: `src/domain/events/events.py` (add event)
- Create: `src/domain/world/travel.py`
- Test: `tests/domain/test_travel.py`

**Interfaces:**
- Consumes: `WorldMap`, `Location` (Task 1); `Game.placements/place` (Task 2); `EventCollector.record` (`domain/events/collector.py:33`); `ActionRejected` (events.py:79).
- Produces:

```python
@dataclass(frozen=True)
class CharacterArrived(BaseEvent):
    character_id: CharacterId
    to_location_id: LocationId
    from_location_id: LocationId | None

@dataclass(frozen=True)
class TravelProposal:
    actor_id: CharacterId
    direction: str  # an exit direction or destination location name

@dataclass(frozen=True)
class TravelResolution:
    accepted: bool
    reason: str          # "" | "unknown_character" | "unknown_exit" | "combat_active"
    location: Location | None

class TravelService:
    def __init__(self, world: WorldMap) -> None: ...
    def resolve(self, game: Game, proposal: TravelProposal, *,
                combat_active: bool, collector: EventCollector) -> TravelResolution
```

- [ ] **Step 1: Failing test**

```python
# tests/domain/test_travel.py
def _bootstrap():  # builds world (T1 helper), game with two placed party members, collector
    ...
def test_travel_moves_actor_and_records_arrival() -> None:
    (world, game, collector, tower_id) = _bootstrap()
    outcome = TravelService(world).resolve(
        game, TravelProposal(actor_id=first, direction="north"),
        combat_active=False, collector=collector)
    assert outcome.accepted and outcome.location.id == tower_id
    assert game.location_of(first) == tower_id
    arrival = collector.events[-1]
    assert arrival.event_type == "character_arrived"
    assert arrival.payload["character_id"] == str(first)

def test_travel_rejections_never_mutate_state() -> None:
    # combat_active=True and unknown direction each yield accepted=False,
    # an ActionRejected envelope, and unchanged placements
```

- [ ] **Step 2: FAIL** (module missing), then implement:

```python
# src/domain/world/travel.py
from dataclasses import dataclass

from domain.common.errors import InvalidActionError  # if a code-level error is wanted for callers
from domain.events.base import BaseEvent
from domain.common.ids import CharacterId, LocationId
from domain.events.collector import EventCollector
from domain.events.events import ActionRejected
from domain.world.game import Game
from domain.world.locations import Location, WorldMap


@dataclass(frozen=True)
class CharacterArrived(BaseEvent):
    character_id: CharacterId
    to_location_id: LocationId
    from_location_id: LocationId | None


@dataclass(frozen=True)
class TravelProposal:
    actor_id: CharacterId
    direction: str


@dataclass(frozen=True)
class TravelResolution:
    accepted: bool
    reason: str
    location: Location | None
    events: tuple[BaseEvent, ...] = ()


class TravelService:
    def __init__(self, world: WorldMap) -> None:
        self._world = world

    def resolve(self, game: Game, proposal: TravelProposal, *,
                combat_active: bool, collector: EventCollector) -> TravelResolution:
        actor = next((c for cid, c in game.characters.items() if cid == proposal.actor_id and not c.is_defeated()), None)
        if actor is None:
            return self._reject(game, proposal, collector, "unknown_character")
        if combat_active:
            return self._reject(game, proposal, collector, "combat_active")
        here = game.location_of(proposal.actor_id)
        destination_id: LocationId | None = None
        if here is not None:
            destination_id = self._world.get(here).is_exit_to(proposal.direction)
        if destination_id is None:
            destination_id = self._destination_by_name(game, proposal.direction, here)
        if destination_id is None:
            return self._reject(game, proposal, collector, "unknown_exit")
        events: list[BaseEvent] = [
            CharacterArrived(character_id=proposal.actor_id,
                             to_location_id=destination_id, from_location_id=here)
        ]
        for envelope in (collector.record(e) for e in events):
            assert envelope.event_type
        game.place(proposal.actor_id, destination_id)
        return TravelResolution(accepted=True, reason="",
                                location=self._world.get(destination_id), events=tuple(events))

    def _destination_by_name(self, game, direction, here):
        return None  # name-based travel is CLI sugar added in Task 5; domain travel is exit-keyed

    def _reject(self, game, proposal, collector, reason: str) -> TravelResolution:
        envelope = collector.record(ActionRejected(actor_id=proposal.actor_id,
                                                   action_type="travel", reason=reason))
        assert envelope.event_type
        return TravelResolution(accepted=False, reason=reason, location=None)
```

Adjust the sketch so every path records exactly one envelope and sets `events` accordingly (accepted: the single `CharacterArrived`; rejected: the single `ActionRejected`). Drop the unused `InvalidActionError` import if unused. Keep `events` on `TravelResolution` synchronised with what was recorded.

- [ ] **Step 3: PASS + full domain suite green** — `.venv/bin/pytest tests/domain -q`

- [ ] **Step 4: Commit** — `feat(domain): deterministic travel resolution with CharacterArrived events`

---

### Task 5: GameService travel command, auto-combat, scene view, CLI `go`

**Files:**
- Modify: `src/application/commands.py` (`TravelCommand`), `src/application/game_service.py`, `src/application/views.py`, `src/session/play.py`, `src/session/factory.py`, `src/interfaces/cli/app.py`, `src/interfaces/cli/renderer.py`
- Test: `tests/application/test_game_service.py` (add), `tests/session/test_play.py` (add), `tests/interfaces/test_cli.py` (add)

**Interfaces:**
- Consumes: `TravelService` (Task 4), `WorldCatalog` (Task 3), `GameService.start_combat` (`game_service.py:158`), `parse_input`/`apply_input` (`session/play.py:38,114`).
- Produces:
  - `@dataclass(frozen=True) class TravelCommand: game_id: GameId; actor_id: CharacterId; direction: str`
  - `GameService.travel(command: TravelCommand) -> TurnReport` — same shape/reject semantics as `submit_action` (`accepted`, `error_code` = trip reason code, events). Persisted like every mutating path (`save(game, drained)`), optimistic lock preserved.
  - Auto-combat rule (domain-adjacent application policy): after an accepted arrival, if **any living enemy of the same side-conflict** (party actor arriving among living enemies, i.e. `game.opponents_of(actor)` intersect `game.residents_of(destination)`) is non-empty **and game is RUNNING**, combat starts via the existing `start_combat` path. Gate change inside `start_combat`: allow when `status == RUNNING` (re-entry scene) in addition to `CREATED`; keep ENDED rejected with the existing error.
  - `GameView` gains `scene: SceneView | None`; `@dataclass(frozen=True) class SceneView: location_id: str; name: str; description: str; exits: list[tuple[str, str]]` (direction → destination name). All existing view construction callers go through `GameService.get_view`, which takes an optional `world: WorldMap | None = None` constructor injection (stored as `self._world`).
  - `parse_input` recognises `go <direction>` → `("travel", argument)`; `apply_input` builds `TravelCommand` for the acting human character (first living party member — same convention the attack path uses for actor resolution in `session/play.py:114-147`) and returns `InputOutcome(kind="travel", ...)` with `turn_report` filled on success, `kind="unknown_exit"` rejection rendered like `no_target`.
  - Renderer: `render_game_view` prints `Scene: <name> — <description>` plus `Exits: north → Eastern Tower` when `view.scene` is set.

- [ ] **Step 1: Failing application test** — add to `tests/application/test_game_service.py`:

```python
def test_travel_command_moves_party_member_and_opens_combat_in_enemy_scene() -> None:
    # two-party game with one enemy placed at location B; party at A; A->B exit exists
    report = service.travel(TravelCommand(game_id=gid, actor_id=hero, direction="north"))
    assert report.accepted
    assert service.get_view(gid).combat is not None  # combat auto-opened at arrival
    assert [e.event_type for e in report.events][-1] in {"combat_started", "turn_started"}

def test_travel_rejected_exit_leaves_placement_untouched() -> None:
    report = service.travel(TravelCommand(game_id=gid, actor_id=hero, direction="west"))
    assert not report.accepted and report.error_code == "unknown_exit"
    assert service.get_view(gid).combat is None
```

- [ ] **Step 2: FAIL** — ` AttributeError: 'GameService' object has no attribute 'travel'`

- [ ] **Step 3: Implement `GameService.travel`**

```python
    def travel(self, command: TravelCommand) -> TurnReport:
        game = self._require_running(command.game_id)  # existing internal helper style
        combat = self._combats.get(command.game_id)
        combat_active = combat is not None and combat.status.value == "active"
        collector = self._collectors[command.game_id]
        outcome = self._travel.resolve(game, TravelProposal(actor_id=command.actor_id,
                                     direction=command.direction), combat_active=combat_active,
                                       collector=collector)
        if not outcome.accepted:
            return TurnReport(game_id=str(command.game_id), accepted=False,
                              error_code=outcome.reason, reason=outcome.reason,
                              events=self._persist(game),  # _persist drains + saves (shape of submit_action, game_service.py:199)
                              view=self.get_view(command.game_id), game_over=False)
        if outcome.location is not None and self._hostiles_at(game, command.actor_id, outcome.location.id):
            return self.start_combat(command.game_id)  # arrival opens combat; events flow through
        return TurnReport(game_id=str(command.game_id), accepted=True, error_code="",
                          reason="", events=self._persist(game),
                          view=self.get_view(command.game_id), game_over=False)
```

Constructor gains `world: WorldMap | None = None`; `_travel = TravelService(world)` when provided (`self._travel = None` otherwise → travel raises `GameNotRunning`-style `InvalidActionError("no world configured")`). `get_view` composes `SceneView` from the first living party member's placement when `world` is set.

- [ ] **Step 4: Session/CLI wiring** — `parse_input` gains before the attack branch:

```python
    if raw.casefold().startswith("go "):
        return ("travel", raw[3:].strip())
```

`apply_input` builds `TravelCommand(game_id=..., actor_id=<first living party id>, direction=...)`, calls `service.travel`; success path triggers `self._gm_react` like the attack path when the report carries `CombatStarted` (so narrators react once). Renderer + CLI dispatch table in `app.py:155` gains `kind == "travel"` → `render_gm_result`/no-op like existing kinds.

`build_session` accepts `world_path: Path | None = None` in `SessionConfig`; when set, it loads the catalog, places the party at `world.start_id` via `game.place(...)` and the `config/encounter.toml` enemies at the location named by `[world] enemies_at`, then passes `world=...` into `GameService`. Default `None` keeps every existing session and test byte-identical.

- [ ] **Step 5: CLI-level test** — extend `tests/session/test_play.py`:

```python
def test_go_travels_when_world_configured() -> None: ...   # "north" → travel outcome, scene moved
def test_go_parses_without_world_as_rejection() -> None: ...  # outcome.kind == "error"/"unknown_exit"
```

Keep both passing with the default (no-world) session.

- [ ] **Step 6: Gates** — `.venv/bin/pytest tests -q --ignore=tests/integration && .venv/bin/ruff check . && .venv/bin/mypy | tail -1`. Commit: `feat(application): travel command with arrival-driven combat, scene view, CLI go verb`.

---

### Task 6: Memory location tags

**Files:**
- Modify: `src/ai/memory/types.py` (`MemoryRecord.location_id: str | None = None`)
- Modify: `src/application/memory/memory_service.py` (situation line + `record_turn`/`retrieve` signatures)
- Modify: `src/application/agents/perception.py` (`AgentPerception.location_id: str | None = None`, from `game.location_of(actor)`)
- Modify: `src/infrastructure/persistence/postgres/migrations/004_agent_memory_locations.sql` (new), pgvector repository + its mapping
- Modify: in-memory memory repository (`src/infrastructure/vector/` or the in-memory repo file — grep `class .*MemoryRepository`)
- Test: `tests/application/memory/` (add), `tests/infrastructure/` memory repo tests (add)

**Interfaces:**
- Produces: `MemoryService.retrieve(..., location_id: str | None = None)` — retrieval keeps records where `location_id is None or kind == SEMANTIC or location_id == current`; `MemoryService.record_turn(..., location_id: str | None = None)` stamps the tag. Repository `search(game_id, agent_id, vector, limit, location_id=None)` and `append` gain the column.
- Migration `004_agent_memory_locations.sql`:

```sql
ALTER TABLE agent_memories ADD COLUMN location_id TEXT;
```

- [ ] **Step 1: Failing tests** — (a) tag round-trip: record two memories for the same agent, one at location A one at location B, retrieve with `location_id=B`: episodic-A text is filtered out, semantic notes survive; (b) `MemoryRecord.location_field` default None keeps every existing test green; (c) pgserver test asserts the migration applies and the column exists.

- [ ] **Step 2: FAIL, implement, PASS** — situation line appended with `location=<name or id>`; deterministic embedder changes are acceptable (embeddings are internal), but keep `tests/` situation-line assertions updated in the same commit.

- [ ] **Step 3: Gates + commit** — `feat(memory): scene-scoped episodic memory tags`

---

### Task 7: Agent scene decisions (talk / travel / wait)

**Files:**
- Create: `src/application/agents/scene_decisions.py`
- Modify: `src/application/agents/perception.py` (scene facts: location name/description/exits, co-residents)
- Test: `tests/application/agents/test_scene_decisions.py`

**Interfaces:**
- Consumes: `AgentRuntime.decide_structured` (`src/ai/agents/runtime.py:34`), `AgentPerception` (perception.py:23), `WorldMap` (Task 1).
- Produces:

```python
SCENE_DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action_type": {"enum": ["talk", "travel", "wait"]},
        "speech": {"type": "string"},
        "exit_direction": {"type": "string"},
        "public_message": {"type": "string"},
    },
    "required": ["action_type", "public_message"],
}

@dataclass(frozen=True)
class SceneDecision:
    action_type: str            # "talk" | "travel" | "wait"
    speech: str | None
    exit_direction: str | None
    public_message: str

def map_scene_decision(data: Mapping[str, object]) -> SceneDecision  # raises InvalidAgentDecisionError
```

- [ ] **Step 1: Failing test** — valid talk (speech required, else `InvalidAgentDecisionError`), travel requires `exit_direction` and rejects directions with no exit **using the perception passed to a validator** `validate_scene_decision(decision, world, game, actor_id) -> str | None` (returns rejection reason string or None); wait always legal.

- [ ] **Step 2: FAIL → implement → PASS.** Validation is pure/predicate-only here; execution lives in Task 8. The schema matches the runtime's `decide_structured` contract (structured JSON via the gateway; retries via `RetryPolicy`).

- [ ] **Step 3: Commit** — `feat(agents): out-of-combat scene decision schema and validation`

---

### Task 8: Scene loop service + CLI loop

**Files:**
- Create: `src/application/scene/scene_service.py`
- Modify: `src/session/factory.py` (wire `SceneService`, world into `GameService`), `src/interfaces/cli/app.py`, `config/game.toml`
- Test: `tests/application/scene/test_scene_service.py`, `tests/interfaces/test_cli.py` (add)

**Interfaces:**
- Consumes: `AgentTurnService.is_agent_controlled` (agent_turn_service.py:89), `TravelCommand`+`GameService.travel` (Task 5), `map_scene_decision` (Task 7), `GmDirector.on_player_say` (director.py:257), `MemoryService` retrieve/record with location tags (Task 6).
- Produces:

```python
@dataclass(frozen=True)
class SceneTick:
    kind: str                # "idle" | "combat_wait" | "scene_action" | "game_over"
    actor_name: str | None
    narration: str | None    # GM reply for talk actions
    events: tuple            # EventEnvelope from travel/atmosphere

@dataclass(frozen=True)
class SceneLoopConfig:
    tick_seconds: float = 0.0         # CLI sleeps between agent actions when > 0
    max_agent_scene_actions: int = 4  # per tick budget (safety cap, §28-style bounded work)

class SceneService:
    def __init__(self, game_service, turn_service: AgentTurnService | None,
                 gm_director, gateway_for_scenes: ModelGateway | None,
                 runtime: AgentRuntime | None, telemetry=None, config: SceneLoopConfig) -> None: ...
    def tick(self, session: GameSession, *, correlation_id: str | None = None) -> SceneTick
```

tick semantics (all deterministic guards, LLM only chooses):
1. `view.status == "ended"` → `SceneTick(kind="game_over")`.
2. combat active → `SceneTick(kind="combat_wait")` (CLI falls through to the normal combat loop; the pause rule is structurally guaranteed because combat turns are driven by `advance()`, never by the scene loop).
3. next living agent-controlled party member in turn order → SceneService asks it for a `SceneDecision`:
   - talk → routed through the same GmDirector task as `respond_to_player` with the speaker's name and scene context (Task 9 scope keeps the one-NPC-voice model),
   - travel → `GameService.travel` (rejections are consumed, counted, never mutate — the agent may retry next tick; after `max_agent_scene_actions` consecutive rejections the actor's turn is skipped deterministically),
   - wait → no-op turn.
4. non-agent (human) turn or no candidate → `SceneTick(kind="idle")` → CLI returns to the prompt (pause rule).

- [ ] **Step 1: Failing test** — a `ScriptedAgentGateway`-scripted scene (gateway returns talk for agent 1, travel for agent 2, wait for agent 3) wired through `build_session(world_path=...)`; assert sequence of `SceneTick.kind`, final placements, one GM reply for the talk, and that a rejected travel increments a local attempt counter without placement change.

- [ ] **Step 2: FAIL → implement → PASS** (application). `config/game.toml`:

```toml
[loop]
tick_seconds = 0.0
max_agent_scene_actions = 4
```

- [ ] **Step 3: CLI integration** — in `app.py`, before each prompt iteration when `view.status == "running"` and combat is not active, call `scene_service.tick()` once and render `SceneTick.narration` when present; `--tick-seconds` CLI flag (default 0.0) overrides `config/game.toml` per §48. The human turn remains the blocking prompt: the pause rule is the existing `advance()`-then-block structure (research §9). `/help` gains the `go` verb; renderer gains the scene line.

- [ ] **Step 4: Gates + commit** — `feat(application): scene loop service with CLI tick wiring`

---

### Task 9: Deterministic full-adventure integration + docs + smoke runbook

**Files:**
- Create: `tests/integration/test_full_adventure_loop.py`
- Modify: `README.md`, `docs/superpowers/plans/README.md` (roadmap row), `config/world.toml` (final scenario tuning)

**Interfaces:** Consumes everything from Tasks 1–8 through `build_session` only (composition root, no per-test re-wiring).

- [ ] **Step 1: Write the adventure test** — `ScriptedAgentGateway` + `ScriptedGmGateway`, no world needed by the gateway:

```python
"""Scene A: party talks (GM replies via ScriptedGmGateway); agent proposes travel north;
arrival at the tower opens combat with tower residents; agents finish it; scene B talk lands."""
def test_full_adventure_loop_talk_travel_combat_talk() -> None:
    session = build_session(SessionConfig(agent_mode="fake", gm_mode="fake",
                                          world_path=WORLD_TOML_FIXTURE))
    # drive: scene ticks until travel accepted → combat opens → agent turns resolve → ended
    # assertions, in order over get_events():
    #   character_arrived(to=tower), combat_started, combat_ended, then game stays usable
    #   (a post-combat scene tick yields a talk reply, not an exception),
    #   and party placements equal tower for the mover / courtyard for the stayers.
```

Expected: PASS fully offline (FakeModelGateway + in-memory repositories).

- [ ] **Step 2: Add the "gate: both" evidence block** to this plan (Milestone results section below), with the recorded live CLI smoke runbook:

```bash
export OPENCODE_API_KEY=...      # real key, shell only
.venv/bin/python -c "import sys; from interfaces.cli.app import main; sys.exit(main(sys.argv[1:]))" --agent llm --gm llm --seed 7
# at the prompt: watch scene loop narration → "go north" → combat resolve → "say ..." in the tower
# record: what worked / agent actions / every break in the talk-travel-combat-talk loop
```

- [ ] **Step 3: Update roadmap** — add row `| 12 | 2026-09-13-full-adventure-loop.md | Phase 21 — locations + travel + scene loop (CLI-first); Phase 22 web exposure | In-progress (awaiting recorded CLI smoke) |` and the Phase 22 candidates (additive `/api/v1` unfreeze: scene/travel event fields, scene-aware GameView, spectator loop endpoint).

- [ ] **Step 4: Final gates** — full offline suite with keys blanked; `ruff check .`; `mypy | tail -1`; confirm no diff outside the declared files:

```bash
git diff --stat HEAD@{1}..HEAD -- src/interfaces/api src/interfaces/web tests/interfaces/web
# Expected: empty
```

- [ ] **Step 5: Commit** — `test(integration): scripted full-adventure loop, docs, live smoke runbook`

---

## Definition of Done

- [ ] Living party/agents can talk in a scene, travel by validated exit, and trigger combat purely by arrival — all event-recorded, all rule-decided by the domain (LLM never sees rule authority).
- [ ] Scene loop pauses exactly on combat/human turns; rejects never mutate state; retry/skip caps are configurable.
- [ ] Episodic memories are scene-tagged; cross-scene semantics still retrieve.
- [ ] Deterministic CI proof works with zero keys; live smoke recorded before Phase 22 planning.
- [ ] Frozen `/api/v1` untouched; no new runtime dependencies; domain stays framework-free.
- [ ] Roadmap updated; plans/README status marks the milestone evidence.

## Milestone results (recorded live CLI smoke)

> **PENDING HUMAN EXECUTION** — fill after running the Task 9 runbook with live keys:
> what worked, which actions agents took, every break in the talk→travel→combat→talk loop.

## Phase 22 candidates (web exposure, gated on the recorded smoke)

- Additive `/api/v1` unfreeze: `scene` block in `GET /games/{id}`/`status`, `character_arrived` in `/events`, `POST /games/{id}/travel` mirroring `TravelCommand`.
- Spectator loop: expose `SceneService.tick` on a server-side timer (MC decisions #3/#9), pause rules identical.
- Remaining candidates from Plan 11 unchanged (SSE, listing endpoint, multi-worker).
