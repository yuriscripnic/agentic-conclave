# Agent Memory + pgvector (Plan 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI party members record episodic/semantic memories per accepted turn and retrieve the most relevant ones into their prompts — a game-free memory platform (`src/ai/memory/`), an application policy service (`MemoryService`), and two swappable backends (in-memory, pgvector).

**Architecture:** Port-first (the Plan 3 treatment). `src/ai/memory/` owns value types + ports and stays game-free (purity-tested like `src/ai/agents/`). `src/application/memory/` owns the policy (derive → batch-embed → append; retrieve → top-k). Infrastructure provides the in-memory backend, the pgvector backend, and an `embed()` method on the existing OpenRouter adapter. `AgentTurnService` gets one optional `memory` kwarg; memory never gates a turn. `src/domain/` is untouched.

**Tech Stack:** Python 3.12 stdlib (hashlib, math, asyncio, dataclasses, enum) for the platform and deterministic embedder; existing httpx/psycopg for adapter and pgvector SQL; pgvector via plain SQL (`<=>` cosine) over the existing connection pattern; pgserver (already a dev dependency) ships the `vector` extension so pgvector tests run offline.

**Spec:** `docs/superpowers/specs/2026-09-06-agent-memory-design.md` (binding — the plan argues from it; the spec carries four plan-writing refinements recorded 2026-09-06: `MemoryService` takes `model: str`, `retrieve`/`record_turn` take an explicit `game_id: str`, `record_turn` takes the note as a plain string, and episodic damage is attributed by matching `DamageApplied.character_id` to the attack's `target_id`).

## Global Constraints

Every task implicitly includes these. From spec §7 plus operational facts:

- **The gate** (run at every task boundary, from the repo/worktree root):
  ```bash
  .venv/bin/python -m ruff check src tests && .venv/bin/python -m mypy && .venv/bin/python -m pytest -q
  ```
  In a fresh worktree there is no `.venv` — use the main checkout's interpreter instead:
  `/home/yss/workspace/agentic-conclave/.venv/bin/python -m ...` (pytest finds `src` via `pythonpath = ["src"]` in `pyproject.toml`).
- **Domain untouched:** `git log master..HEAD --oneline -- src/domain` must print nothing at every gate.
- **Test-count chain** (offline suite; baseline 308): T1 → 314, T2 → 321, T3 → 328, T4 → 333, T5 → 343, T6 → 349, T7 → 355, T8 → 361, T9 → 362. One additional live test exists in `tests/integration/test_openrouter_live.py` and only runs when `OPENROUTER_API_KEY` is set (363 with the key).
- **The single config carve-out:** `[profiles.embedding]` = `openai/text-embedding-3-small` (explicit user decision 2026-09-06). Every chat profile stays `z-ai/glm-5.3-flash`.
- **No new runtime dependencies.** stdlib-only platform; pgvector is plain SQL over the existing psycopg connection; httpx/psycopg/pgserver are already installed.
- **Memory never gates a turn:** only `ModelError` and `PersistenceError` are swallowed at memory boundaries; anything else propagates. Invalid LLM actions can never corrupt state through the memory path.
- **Memory contents never leave the owning agent's prompt** (§20, §34): no logging, no CLI display — only the `memory_retrieved` count. Never log API keys or credentials.
- **Offline discipline:** the full suite is green without `OPENROUTER_API_KEY` or `DATABASE_URL`; `--agent fake` never touches the network (deterministic embedder).
- **No `__init__.py` in test directories; test-file basenames unique repo-wide** (there is already a `tests/ai/agents/test_purity.py`, hence `test_memory_purity.py` in Task 1).
- **Commits:** conventional, scoped by layer, each ending with the trailer `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- **mypy strict + ruff (line-length 100)** are clean at every gate. Keep every source line ≤ 100 chars.

---

### Task 1: `src/ai/memory/` — value types, ports, purity test

**Files:**
- Create: `src/ai/memory/__init__.py`
- Create: `src/ai/memory/types.py`
- Create: `src/ai/memory/ports.py`
- Test: `tests/ai/memory/test_embedding_types.py`
- Test: `tests/ai/memory/test_memory_purity.py`

**Interfaces:**
- Consumes: `Usage`, `LLMInvocation` from `src/ai/models/types.py` (existing).
- Produces (used by Tasks 2–9): `MemoryKind` (StrEnum: `EPISODIC="episodic"`, `SEMANTIC="semantic"`); frozen `MemoryRecord(memory_id: str, game_id: str, agent_key: str, kind: MemoryKind, text: str, round_number: int | None, embedding: tuple[float, ...])`; frozen `EmbeddingRequest(texts: tuple[str, ...], model: str, timeout_seconds: float = 60.0)`; frozen `EmbeddingResponse(vectors: tuple[tuple[float, ...], ...], usage: Usage, invocation: LLMInvocation)`; `@runtime_checkable EmbeddingGateway` Protocol with `async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse`; `@runtime_checkable MemoryRepository` Protocol with `def append(self, record: MemoryRecord) -> None` and `def search(self, game_id: str, agent_key: str, query: tuple[float, ...], limit: int) -> tuple[MemoryRecord, ...]`.

- [ ] **Step 1: Write the failing tests**

`tests/ai/memory/test_embedding_types.py`:

```python
"""Memory platform value types and ports (spec §3.1)."""

import dataclasses

import pytest

from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.memory.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    MemoryKind,
    MemoryRecord,
)
from ai.models.types import LLMInvocation, Usage


def _invocation() -> LLMInvocation:
    return LLMInvocation(
        provider="deterministic",
        model="test-model",
        operation="embed",
        status="ok",
        error_kind=None,
        latency_ms=0,
        input_tokens=3,
        output_tokens=0,
        estimated_cost_usd=None,
        request_id="req-1",
    )


def test_memory_kind_values_match_the_persisted_labels() -> None:
    assert MemoryKind.EPISODIC.value == "episodic"
    assert MemoryKind.SEMANTIC.value == "semantic"


def test_memory_record_is_frozen() -> None:
    record = MemoryRecord(
        memory_id="mem-1",
        game_id="game-1",
        agent_key="brix",
        kind=MemoryKind.EPISODIC,
        text="Round 1: attacked Goblin.",
        round_number=1,
        embedding=(1.0, 0.0),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.text = "mutated"  # type: ignore[misc]


def test_embedding_request_defaults_to_sixty_second_timeout() -> None:
    request = EmbeddingRequest(texts=("hello",), model="test-model")
    assert request.texts == ("hello",)
    assert request.model == "test-model"
    assert request.timeout_seconds == 60.0


def test_embedding_response_is_frozen() -> None:
    response = EmbeddingResponse(
        vectors=((1.0, 0.0),),
        usage=Usage(input_tokens=3, output_tokens=0),
        invocation=_invocation(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        response.vectors = ((0.0, 1.0),)  # type: ignore[misc]


def test_ports_accept_structural_implementations() -> None:
    class _StubEmbedder:
        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            raise AssertionError("not called")

    class _StubRepository:
        def append(self, record: MemoryRecord) -> None:
            raise AssertionError("not called")

        def search(
            self,
            game_id: str,
            agent_key: str,
            query: tuple[float, ...],
            limit: int,
        ) -> tuple[MemoryRecord, ...]:
            return ()

    assert isinstance(_StubEmbedder(), EmbeddingGateway)
    assert isinstance(_StubRepository(), MemoryRepository)
```

`tests/ai/memory/test_memory_purity.py` (mirrors `tests/ai/agents/test_purity.py`):

```python
"""src/ai/memory must stay game-free: no domain/application/infrastructure imports."""

import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "ai" / "memory"
_FORBIDDEN_ROOTS = {"domain", "application", "interfaces", "infrastructure"}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_memory_package_imports_only_ai_and_stdlib() -> None:
    offenders = {
        f"{path.name}: {sorted(roots & _FORBIDDEN_ROOTS)}"
        for path in _PACKAGE.glob("*.py")
        if (roots := _imported_roots(path)) & _FORBIDDEN_ROOTS
    }
    assert offenders == set()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/memory -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.memory'`.

- [ ] **Step 3: Implement the package**

`src/ai/memory/__init__.py`:

```python
"""Memory platform: value types, ports, and the offline embedder (game-free)."""
```

`src/ai/memory/types.py`:

```python
"""Value types for the memory platform (spec §3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai.models.types import LLMInvocation, Usage


class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class MemoryRecord:
    """One persisted agent memory; embedding is mandatory (embed before append)."""

    memory_id: str
    game_id: str
    agent_key: str
    kind: MemoryKind
    text: str
    round_number: int | None
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingRequest:
    """Batch embedding request: one call embeds all inputs."""

    texts: tuple[str, ...]
    model: str
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class EmbeddingResponse:
    """Vectors are parallel to the request's texts."""

    vectors: tuple[tuple[float, ...], ...]
    usage: Usage
    invocation: LLMInvocation
```

`src/ai/memory/ports.py`:

```python
"""Memory platform ports — the only memory seams (spec §3.1, CLAUDE.md §7)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai.memory.types import EmbeddingRequest, EmbeddingResponse, MemoryRecord


@runtime_checkable
class EmbeddingGateway(Protocol):
    """Single-attempt embedding transport; retry policy belongs to the caller."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


@runtime_checkable
class MemoryRepository(Protocol):
    """Append + cosine search scoped to one (game, agent) pair."""

    def append(self, record: MemoryRecord) -> None: ...

    def search(
        self,
        game_id: str,
        agent_key: str,
        query: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryRecord, ...]: ...
```

Note: `__protocol_members__` is unavailable on Python 3.12, hence the `@runtime_checkable` + `isinstance` approach in the port test.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/memory -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full gate**

Run the gate from Global Constraints.
Expected: ruff/mypy clean; pytest 314 passed, 1 skipped (offline count 314; the skip is the live test without `OPENROUTER_API_KEY`).

- [ ] **Step 6: Commit**

```bash
git add src/ai/memory tests/ai/memory
git commit -m "feat(ai): add memory platform types and ports

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `DeterministicEmbeddingGateway` — offline embedder

**Files:**
- Create: `src/ai/memory/fake.py`
- Test: `tests/ai/memory/test_deterministic_embedding.py`

**Interfaces:**
- Consumes: `EmbeddingRequest`/`EmbeddingResponse` from Task 1.
- Produces: `DeterministicEmbeddingGateway` — satisfies `EmbeddingGateway` structurally; class constants `DIM = 256`, `PROVIDER = "deterministic"`. Tokenizer: lowercase, whitespace-split, keep only `str.isalnum()` characters per token (drops punctuation), skip empties. Each token blake2b-hashed into one bucket; vector L2-normalized (zero vector when no tokens). Used by Tasks 5, 8, 9 and every offline test.

- [ ] **Step 1: Write the failing tests**

`tests/ai/memory/test_deterministic_embedding.py`:

```python
"""DeterministicEmbeddingGateway: offline, reproducible embeddings (spec §3.1)."""

import asyncio
import math

from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.types import EmbeddingRequest, EmbeddingResponse


def _embed(*texts: str) -> EmbeddingResponse:
    gateway = DeterministicEmbeddingGateway()
    return asyncio.run(
        gateway.embed(EmbeddingRequest(texts=texts, model="test-model"))
    )


def test_same_text_same_vector_across_instances_and_calls() -> None:
    first = _embed("Brix attacked the Goblin.")
    second = _embed("Brix attacked the Goblin.")
    assert first.vectors == second.vectors


def test_vectors_are_fixed_dimension_and_unit_length() -> None:
    vector = _embed("Brix attacked the Goblin.").vectors[0]
    assert len(vector) == DeterministicEmbeddingGateway.DIM
    assert math.isclose(sum(value * value for value in vector), 1.0, rel_tol=1e-9)


def test_batch_texts_map_to_parallel_vectors() -> None:
    response = _embed("alpha", "beta", "gamma")
    assert len(response.vectors) == 3


def test_related_texts_score_higher_than_unrelated() -> None:
    response = _embed(
        "the orc hits hard stay at range",
        "the orc hits hard",
        "zebra quantum piano",
    )

    def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b))

    assert dot(response.vectors[0], response.vectors[1]) > dot(
        response.vectors[0], response.vectors[2]
    )


def test_punctuation_and_case_do_not_change_the_vector() -> None:
    response = _embed("Goblin!", "goblin")
    assert response.vectors[0] == response.vectors[1]


def test_empty_text_yields_a_zero_vector() -> None:
    response = _embed("   ")
    assert response.vectors[0] == (0.0,) * DeterministicEmbeddingGateway.DIM


def test_invocation_metadata_records_the_embed_operation() -> None:
    response = _embed("hello world")
    assert response.invocation.provider == "deterministic"
    assert response.invocation.model == "test-model"
    assert response.invocation.operation == "embed"
    assert response.invocation.status == "ok"
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens == 0
    assert response.invocation.estimated_cost_usd is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/ai/memory/test_deterministic_embedding.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.memory.fake'`.

- [ ] **Step 3: Implement `src/ai/memory/fake.py`**

```python
"""Deterministic stdlib embedder for tests and offline runs (spec §2 Decision 9)."""

import hashlib
import math
import time
import uuid

from ai.memory.types import EmbeddingRequest, EmbeddingResponse
from ai.models.types import LLMInvocation, Usage


class DeterministicEmbeddingGateway:
    """Hash-based embedder: word buckets, L2-normalized; zero cost, fully offline."""

    DIM = 256
    PROVIDER = "deterministic"

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        started = time.perf_counter()
        vectors = tuple(self._embed_one(text) for text in request.texts)
        tokens = sum(len(self._tokens(text)) for text in request.texts)
        usage = Usage(input_tokens=tokens, output_tokens=0)
        invocation = LLMInvocation(
            provider=self.PROVIDER,
            model=request.model,
            operation="embed",
            status="ok",
            error_kind=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=tokens,
            output_tokens=0,
            estimated_cost_usd=None,
            request_id=uuid.uuid4().hex,
        )
        return EmbeddingResponse(vectors=vectors, usage=usage, invocation=invocation)

    def _embed_one(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.DIM
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self.DIM
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(value / norm for value in vector)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        tokens: list[str] = []
        for raw in text.lower().split():
            token = "".join(character for character in raw if character.isalnum())
            if token:
                tokens.append(token)
        return tokens
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/memory/test_deterministic_embedding.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 321.

- [ ] **Step 6: Commit**

```bash
git add src/ai/memory/fake.py tests/ai/memory/test_deterministic_embedding.py
git commit -m "feat(ai): add deterministic embedding gateway

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: `InMemoryMemoryRepository` — first backend

**Files:**
- Create: `src/infrastructure/memory/__init__.py`
- Create: `src/infrastructure/memory/in_memory.py`
- Test: `tests/infrastructure/memory/test_in_memory_repository.py`

**Interfaces:**
- Consumes: `MemoryRecord`/`MemoryKind` from Task 1.
- Produces: `InMemoryMemoryRepository` — satisfies `MemoryRepository` structurally. `append` is a no-op for an exact duplicate `(game_id, agent_key, kind, text)` (first write wins); `search` returns the most cosine-similar records first, scoped to `(game_id, agent_key)`; `limit <= 0` → `()`. Same contract pgvector implements in Task 7.

- [ ] **Step 1: Write the failing tests**

`tests/infrastructure/memory/test_in_memory_repository.py`:

```python
"""InMemoryMemoryRepository: cosine search + duplicate suppression (spec §3.2)."""

import uuid

from ai.memory.types import MemoryKind, MemoryRecord
from infrastructure.memory.in_memory import InMemoryMemoryRepository


def _record(
    game_id: str,
    agent_key: str,
    text: str,
    embedding: tuple[float, ...],
    *,
    kind: MemoryKind = MemoryKind.EPISODIC,
    round_number: int | None = 1,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=uuid.uuid4().hex,
        game_id=game_id,
        agent_key=agent_key,
        kind=kind,
        text=text,
        round_number=round_number,
        embedding=embedding,
    )


def test_search_returns_the_most_similar_memory_first() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "near", (1.0, 0.0)))
    repo.append(_record("g1", "brix", "far", (0.0, 1.0)))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert [record.text for record in results] == ["near", "far"]


def test_search_scopes_to_game_and_agent() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "mine", (1.0, 0.0)))
    repo.append(_record("g1", "mira", "other agent", (1.0, 0.0)))
    repo.append(_record("g2", "brix", "other game", (1.0, 0.0)))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert [record.text for record in results] == ["mine"]


def test_search_respects_the_limit() -> None:
    repo = InMemoryMemoryRepository()
    for index in range(3):
        repo.append(_record("g1", "brix", f"memory {index}", (1.0, 0.0)))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=2)

    assert len(results) == 2


def test_search_of_an_unknown_scope_is_empty() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "near", (1.0, 0.0)))

    assert repo.search("nowhere", "brix", (1.0, 0.0), limit=5) == ()
    assert repo.search("g1", "nobody", (1.0, 0.0), limit=5) == ()


def test_search_with_non_positive_limit_is_empty() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "near", (1.0, 0.0)))

    assert repo.search("g1", "brix", (1.0, 0.0), limit=0) == ()


def test_exact_duplicate_append_is_a_noop() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _record("g1", "brix", "same text", (1.0, 0.0), kind=MemoryKind.SEMANTIC)
    )
    repo.append(
        _record("g1", "brix", "same text", (0.0, 1.0), kind=MemoryKind.SEMANTIC)
    )

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert len(results) == 1
    assert results[0].embedding == (1.0, 0.0)  # first write wins


def test_duplicate_key_includes_kind() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(_record("g1", "brix", "same text", (1.0, 0.0), kind=MemoryKind.EPISODIC))
    repo.append(_record("g1", "brix", "same text", (1.0, 0.0), kind=MemoryKind.SEMANTIC))

    results = repo.search("g1", "brix", (1.0, 0.0), limit=5)

    assert len(results) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/memory -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.memory'`.

- [ ] **Step 3: Implement the backend**

`src/infrastructure/memory/__init__.py`:

```python
"""Memory repository backends (in-memory and pgvector)."""
```

`src/infrastructure/memory/in_memory.py`:

```python
"""In-memory MemoryRepository — same append/search contract as pgvector (spec §3.2)."""

from __future__ import annotations

import math

from ai.memory.types import MemoryKind, MemoryRecord


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryMemoryRepository:
    """List of records + pure-python cosine; exact-duplicate appends are no-ops."""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._seen: set[tuple[str, str, MemoryKind, str]] = set()

    def append(self, record: MemoryRecord) -> None:
        key = (record.game_id, record.agent_key, record.kind, record.text)
        if key in self._seen:
            return
        self._seen.add(key)
        self._records.append(record)

    def search(
        self,
        game_id: str,
        agent_key: str,
        query: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryRecord, ...]:
        if limit <= 0:
            return ()
        scoped = [
            record
            for record in self._records
            if record.game_id == game_id and record.agent_key == agent_key
        ]
        scored = sorted(
            scoped,
            key=lambda record: _cosine(query, record.embedding),
            reverse=True,
        )
        return tuple(scored[:limit])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/memory -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 328.

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/memory tests/infrastructure/memory
git commit -m "feat(infrastructure): add in-memory memory repository

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: `memory_note` in the decision schema + the "Memories:" prompt section

**Files:**
- Modify: `src/application/agents/character_agent.py`
- Test: `tests/application/agents/test_character_agent.py` (append 5 tests, add imports)

**Interfaces:**
- Consumes: `MemoryRecord`/`MemoryKind` from Task 1.
- Produces (used by Tasks 5 and 8): `ATTACK_DECISION_SCHEMA` gains optional `"memory_note": {"type": "string"}` (NOT in `required`); `AgentDecision` gains `memory_note: str | None = None`; `build_user_prompt(perception, *, rejection=None, party_messages=(), memories: tuple[MemoryRecord, ...] = ())` renders a `Memories:` section (after the Party chatter block, before the Turn order line) as `- [{kind.value}] {text}` in caller order (most-relevant first is the caller's contract), omitted when empty. Mapping rules for `memory_note`: missing/empty/whitespace/non-string → `None`; otherwise collapse whitespace and truncate to 200 chars — never a rejection. The shared private helper `_map_party_message` is renamed `_map_note` and used for both fields; the constant `_PARTY_MESSAGE_MAX_CHARS` is renamed `_NOTE_MAX_CHARS`.

- [ ] **Step 1: Write the failing tests**

In `tests/application/agents/test_character_agent.py`, add to the imports:

```python
from ai.memory.types import MemoryKind, MemoryRecord
```

Then append:

```python
def test_schema_allows_optional_memory_note() -> None:
    validate_against_schema(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "x",
            "memory_note": "The orc hits hard.",
        },
        ATTACK_DECISION_SCHEMA,
    )  # does not raise


def test_schema_rejects_non_string_memory_note() -> None:
    with pytest.raises(ModelInvalidResponseError):
        validate_against_schema(
            {
                "action_type": "attack",
                "target_id": "gob",
                "public_message": "x",
                "memory_note": 7,
            },
            ATTACK_DECISION_SCHEMA,
        )


def test_map_decision_memory_note_normalization() -> None:
    agent = CharacterAgent(_PROFILE)
    collapsed = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": "  The orc\nhits hard!  ",
        },
        _perception(),
    )
    truncated = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": "x" * 500,
        },
        _perception(),
    )
    silent = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": "   ",
        },
        _perception(),
    )
    numeric = agent.map_decision(
        {
            "action_type": "attack",
            "target_id": "gob",
            "public_message": "hi",
            "memory_note": 7,
        },
        _perception(),
    )

    assert collapsed.memory_note == "The orc hits hard!"
    assert truncated.memory_note is not None
    assert len(truncated.memory_note) == 200
    assert silent.memory_note is None
    assert numeric.memory_note is None


def test_user_prompt_renders_memories_section() -> None:
    memories = (
        MemoryRecord(
            memory_id="m1",
            game_id="g",
            agent_key="brix",
            kind=MemoryKind.SEMANTIC,
            text="The orc hits hard — stay at range.",
            round_number=2,
            embedding=(1.0,),
        ),
        MemoryRecord(
            memory_id="m2",
            game_id="g",
            agent_key="brix",
            kind=MemoryKind.EPISODIC,
            text="Round 1: attacked Goblin and missed.",
            round_number=1,
            embedding=(0.5,),
        ),
    )
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), memories=memories)

    assert "Memories:" in prompt
    assert "- [semantic] The orc hits hard — stay at range." in prompt
    assert "- [episodic] Round 1: attacked Goblin and missed." in prompt
    assert prompt.count("HP") == 1  # memories never leak enemy stats
    assert "Turn order" in prompt


def test_user_prompt_omits_the_memories_section_when_empty() -> None:
    prompt = CharacterAgent(_PROFILE).build_user_prompt(_perception(), memories=())

    assert "Memories:" not in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_character_agent.py -q`
Expected: FAIL — `memory_note` unknown to schema (`ModelInvalidResponseError` on the allow-test) and `AttributeError`-style failures on the prompt tests.

- [ ] **Step 3: Modify `src/application/agents/character_agent.py`**

(a) Add the import (first-party group, before `application.agents.party_board`):

```python
from ai.memory.types import MemoryRecord
```

(b) In `ATTACK_DECISION_SCHEMA`, add `"memory_note"` after `"party_message"`:

```python
        "party_message": {"type": "string"},
        "memory_note": {"type": "string"},
```

(c) Rename the constant:

```python
_NOTE_MAX_CHARS = 200
```

(d) `AgentDecision` gains the field:

```python
@dataclass(frozen=True)
class AgentDecision:
    proposal: AttackProposal
    public_message: str
    party_message: str | None = None
    memory_note: str | None = None
```

(e) `build_system_prompt` — replace the two chat rules and the JSON line so the full return becomes:

```python
    def build_system_prompt(self) -> str:
        return (
            f"You are {self._profile.character_name}, a {self._profile.character_class} "
            "in a tabletop role-playing combat.\n"
            f"Personality: {self._profile.persona}\n"
            f"Objective: {self._profile.objective}\n"
            "\n"
            "Rules:\n"
            "- You may only take the attack action.\n"
            "- Choose exactly one target_id from the opponents listed in the user message.\n"
            "- You may include party_message: one short sentence coordinating with your "
            "allies. Omit it to stay silent.\n"
            "- You may include memory_note: one short durable fact worth remembering in "
            "later rounds (for example which foe hits hardest). Omit it if nothing is "
            "worth noting.\n"
            '- Reply ONLY with a JSON object: action_type ("attack"), target_id (string), '
            "public_message (a short first-person battle cry or rationale; never hidden "
            "reasoning), and optionally party_message and memory_note (each one short "
            "sentence).\n"
            "- No other keys, no prose outside the JSON."
        )
```

(f) `build_user_prompt` — new signature and the Memories block. The signature becomes:

```python
    def build_user_prompt(
        self,
        perception: AgentPerception,
        *,
        rejection: str | None = None,
        party_messages: tuple[PartyMessage, ...] = (),
        memories: tuple[MemoryRecord, ...] = (),
    ) -> str:
```

and the body inserts the Memories block between the chatter block and the Turn order line:

```python
        if party_messages:
            lines.append("Party chatter:")
            lines.extend(
                f"- {message.actor_name} (round {message.round_number}): {message.text}"
                for message in party_messages
            )
        if memories:
            lines.append("Memories:")
            lines.extend(
                f"- [{memory.kind.value}] {memory.text}" for memory in memories
            )
        lines.append(f"Turn order: {', '.join(perception.initiative_order)}")
```

(g) In `map_decision`'s return, replace the `party_message=...` line and add the note:

```python
        return AgentDecision(
            proposal=AttackProposal(
                actor_id=CharacterId(perception.active_actor_id),
                target_id=CharacterId(target_id),
            ),
            public_message=public_message.strip(),
            party_message=self._map_note(data.get("party_message")),
            memory_note=self._map_note(data.get("memory_note")),
        )
```

(h) Rename the static mapper:

```python
    @staticmethod
    def _map_note(raw: object) -> str | None:
        """Cosmetic fields are never a rejection — silence, collapse, truncate (spec §3.4)."""
        if not isinstance(raw, str):
            return None
        collapsed = " ".join(raw.split())
        if not collapsed:
            return None
        return collapsed[:_NOTE_MAX_CHARS]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents -q`
Expected: PASS — all existing tests plus the 5 new ones (24 total in the file).

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 333.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/character_agent.py tests/application/agents/test_character_agent.py
git commit -m "feat(application): add memory_note decisions and memory-aware prompts

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: `MemoryService` — the policy layer

**Files:**
- Create: `src/application/memory/__init__.py`
- Create: `src/application/memory/memory_service.py`
- Test: `tests/application/memory/test_memory_service.py`

**Interfaces:**
- Consumes: `EmbeddingGateway`, `MemoryRepository` (Task 1), `DeterministicEmbeddingGateway` (Task 2), `InMemoryMemoryRepository` (Task 3), `AgentPerception` (existing), `TurnReport` (existing, `application.views`), `EventEnvelope` fields (`event_type: str`, `payload: dict[str, object]`).
- Produces (used by Tasks 8 and 9): `MemoryService(gateway, repository, *, model: str, retrieval_limit: int = 5)` with:
  - `retrieve(game_id: str, perception: AgentPerception) -> tuple[MemoryRecord, ...]` — embeds the situation line `"{name} the {class}; round {n}; opponents: {names}"`, searches `(game_id, perception.self_view.id)`, returns top-`retrieval_limit`.
  - `record_turn(game_id: str, perception: AgentPerception, turn_report: TurnReport, *, note: str | None = None) -> None` — no-op when `turn_report.accepted` is False; otherwise derives the episodic text from events (or writes nothing when there is no `attack_resolved` for this actor), takes `note` verbatim as semantic, batch-embeds both texts in ONE call, appends with dedup.
  - Module-level `_episodic_text(perception, turn_report) -> str | None` implementing spec Decision 6 (damage attributed by matching `DamageApplied.character_id` to the attack's `target_id`; format `"Round {n}: attacked {target} and dealt {total} damage"` / `"... and missed"`, optional `" (critical)"`, optional `"; {target} fell"`, trailing period; names resolved via perception, unknown ids fall back to the raw id).

- [ ] **Step 1: Write the failing tests**

`tests/application/memory/test_memory_service.py` (game helpers are duplicated from `tests/application/agents/test_agent_turn_service.py` — test directories have no `__init__.py`, so cross-file imports are impossible; this duplication is the established pattern):

```python
"""MemoryService: episodic derivation, semantic notes, batch embedding, retrieval."""

import asyncio
import dataclasses
import uuid

from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.types import EmbeddingRequest, EmbeddingResponse, MemoryKind, MemoryRecord
from application.agents.perception import AgentPerception, OpponentBrief, build_perception
from application.commands import (
    AddCharacterCommand,
    CreateGameCommand,
    SubmitActionCommand,
    WeaponSpec,
)
from application.game_service import GameService
from application.memory.memory_service import MemoryService, _episodic_text
from application.views import CharacterView, TurnReport
from domain.common.ids import CharacterId, EventId, GameId
from domain.events.collector import EventEnvelope
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.memory.in_memory import InMemoryMemoryRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


class _CapturingEmbeddingGateway:
    """Deterministic embedder that records every request (test double)."""

    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []
        self._inner = DeterministicEmbeddingGateway()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.requests.append(request)
        return await self._inner.embed(request)


def _seed_record(
    game_id: str, agent_key: str, text: str, kind: MemoryKind, round_number: int
) -> MemoryRecord:
    vector = asyncio.run(
        DeterministicEmbeddingGateway().embed(
            EmbeddingRequest(texts=(text,), model="test-model")
        )
    ).vectors[0]
    return MemoryRecord(
        memory_id=uuid.uuid4().hex,
        game_id=game_id,
        agent_key=agent_key,
        kind=kind,
        text=text,
        round_number=round_number,
        embedding=vector,
    )


def _perception() -> AgentPerception:
    me = CharacterView(
        id="brix",
        name="Brix",
        character_class="fighter",
        level=1,
        hp_current=10,
        hp_max=12,
        armor_class=16,
        conditions=[],
        is_defeated=False,
    )
    return AgentPerception(
        round_number=2,
        active_actor_id="brix",
        self_view=me,
        opponents=(
            OpponentBrief(id="gob", name="Goblin", is_defeated=False),
            OpponentBrief(id="orc", name="Orc", is_defeated=True),
        ),
        initiative_order=("Brix", "Goblin", "Arin"),
    )


def _game_service() -> GameService:
    event_store = InMemoryEventRepository()
    return GameService(InMemoryGameRepository(event_store), event_store)


def _fighter(name: str) -> AddCharacterCommand:
    return AddCharacterCommand(
        name=name,
        character_type="player",
        character_class="fighter",
        level=1,
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
        armor_class=16,
        speed_ft=30,
        max_hp=12,
        weapon=WeaponSpec(
            weapon_id="longsword",
            name="Longsword",
            damage_die_count=1,
            damage_die_size=8,
        ),
    )


def _goblin() -> AddCharacterCommand:
    return AddCharacterCommand(
        name="Goblin",
        character_type="enemy",
        level=1,
        strength=8,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=8,
        charisma=8,
        armor_class=13,
        speed_ft=30,
        max_hp=7,
        weapon=WeaponSpec(
            weapon_id="scimitar",
            name="Scimitar",
            damage_die_count=1,
            damage_die_size=6,
        ),
    )


def _brix_first(
    game_service: GameService,
) -> tuple[GameId, CharacterId, CharacterId]:
    """Create Arin + Brix + Goblin, start combat; find a seed where Brix acts first."""
    for seed in range(1, 500):
        game_id = game_service.create_game(CreateGameCommand(seed=seed))
        game_service.add_character(game_id, _fighter("Arin"))
        brix_id = game_service.add_character(game_id, _fighter("Brix"))
        goblin_id = game_service.add_character(game_id, _goblin())
        game_service.start_combat(game_id)
        view = game_service.get_view(game_id)
        if view.combat is not None and view.combat.active_actor_id == brix_id.value:
            return game_id, brix_id, goblin_id
    raise AssertionError("no seed in 1..499 lets Brix act first")


```

The tests:

```python
def test_retrieve_on_an_empty_repository_returns_nothing() -> None:
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )

    assert service.retrieve("game-1", _perception()) == ()


def test_retrieve_builds_the_query_from_the_perception() -> None:
    gateway = _CapturingEmbeddingGateway()
    service = MemoryService(gateway, InMemoryMemoryRepository(), model="test-model")

    service.retrieve("game-1", _perception())

    assert len(gateway.requests) == 1
    assert gateway.requests[0].model == "test-model"
    query = gateway.requests[0].texts[0]
    assert "Brix" in query
    assert "fighter" in query
    assert "round 2" in query
    assert "Goblin" in query
    assert "Orc" in query


def test_retrieve_returns_relevant_memories_first() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _seed_record("game-1", "brix", "The Goblin hits hard — stay at range.",
                     MemoryKind.SEMANTIC, 1)
    )
    repo.append(
        _seed_record("game-1", "brix", "Zebra quantum piano fortissimo.",
                     MemoryKind.SEMANTIC, 1)
    )
    service = MemoryService(
        DeterministicEmbeddingGateway(), repo, model="test-model"
    )

    memories = service.retrieve("game-1", _perception())

    assert memories[0].text == "The Goblin hits hard — stay at range."


def test_retrieve_respects_the_retrieval_limit() -> None:
    repo = InMemoryMemoryRepository()
    repo.append(
        _seed_record("game-1", "brix", "Goblin hits hard stay at range",
                     MemoryKind.SEMANTIC, 1)
    )
    repo.append(
        _seed_record("game-1", "brix", "Zebra quantum piano fortissimo",
                     MemoryKind.SEMANTIC, 1)
    )
    service = MemoryService(
        DeterministicEmbeddingGateway(), repo, model="test-model", retrieval_limit=1
    )

    memories = service.retrieve("game-1", _perception())

    assert len(memories) == 1
    assert memories[0].text == "Goblin hits hard stay at range"


def test_record_turn_writes_episodic_memory_from_a_real_turn() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)

    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )
    service.record_turn(str(game_id), perception, turn_report)

    memories = service.retrieve(str(game_id), perception)
    episodic = [record for record in memories if record.kind is MemoryKind.EPISODIC]
    assert len(episodic) == 1
    assert episodic[0].text.startswith("Round 1: attacked Goblin and ")
    assert episodic[0].round_number == 1


def test_record_turn_writes_the_semantic_note_verbatim() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(
        str(game_id), perception, turn_report, note="The goblin bleeds — finish it."
    )

    memories = service.retrieve(str(game_id), perception)
    semantic = [record for record in memories if record.kind is MemoryKind.SEMANTIC]
    assert len(semantic) == 1
    assert semantic[0].text == "The goblin bleeds — finish it."


def test_record_turn_batches_all_texts_into_one_embed_call() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    gateway = _CapturingEmbeddingGateway()
    service = MemoryService(gateway, InMemoryMemoryRepository(), model="test-model")
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(str(game_id), perception, turn_report, note="Watch the Goblin.")

    assert len(gateway.requests) == 1
    assert len(gateway.requests[0].texts) == 2


def test_record_turn_without_an_accepted_attack_writes_nothing() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=CharacterId("nobody"),
        )
    )

    service.record_turn(str(game_id), perception, turn_report, note="should not persist")

    assert turn_report.accepted is False
    assert service.retrieve(str(game_id), perception) == ()


def test_record_turn_dedupes_identical_records() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    service = MemoryService(
        DeterministicEmbeddingGateway(), InMemoryMemoryRepository(), model="test-model"
    )
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    service.record_turn(str(game_id), perception, turn_report, note="Same note.")
    service.record_turn(str(game_id), perception, turn_report, note="Same note.")

    memories = service.retrieve(str(game_id), perception)
    assert len(memories) == 2  # one episodic + one semantic, no duplicates
    assert len({record.kind for record in memories}) == 2


def test_episodic_derivation_covers_hit_miss_critical_defeat_and_no_attack() -> None:
    """Spec §5: pin every derivation branch deterministically with synthetic events."""
    game_service = _game_service()
    game_id, brix_id, goblin_id = _brix_first(game_service)
    perception = build_perception(game_service.get_view(game_id), brix_id.value)
    turn_report = game_service.submit_action(
        SubmitActionCommand(
            game_id=game_id,
            actor_id=brix_id,
            action_type="attack",
            target_id=goblin_id,
        )
    )

    def envelope(event_type: str, payload: dict[str, object]) -> EventEnvelope:
        return EventEnvelope(
            sequence=1,
            event_id=EventId.generate(),
            game_id=game_id,
            occurred_at="2026-09-06T00:00:00+00:00",
            event_type=event_type,
            payload=payload,
        )

    def report_with(*events: EventEnvelope) -> TurnReport:
        return dataclasses.replace(turn_report, events=list(events))

    def attack_payload(hit: bool, critical: bool) -> dict[str, object]:
        return {
            "attacker_id": brix_id.value,
            "target_id": goblin_id.value,
            "hit": hit,
            "critical": critical,
        }

    damage = envelope("damage_applied", {"character_id": goblin_id.value, "amount": 5})
    defeat = envelope("character_defeated", {"character_id": goblin_id.value})
    hit = envelope("attack_resolved", attack_payload(True, False))
    critical = envelope("attack_resolved", attack_payload(True, True))
    miss = envelope("attack_resolved", attack_payload(False, False))

    assert _episodic_text(perception, report_with(hit, damage)) == (
        "Round 1: attacked Goblin and dealt 5 damage."
    )
    assert _episodic_text(perception, report_with(critical, damage)) == (
        "Round 1: attacked Goblin and dealt 5 damage (critical)."
    )
    assert _episodic_text(perception, report_with(miss)) == (
        "Round 1: attacked Goblin and missed."
    )
    assert _episodic_text(perception, report_with(miss, defeat)) == (
        "Round 1: attacked Goblin and missed; Goblin fell."
    )
    # Damage without an attack_resolved for this actor derives nothing (Decision 6).
    assert _episodic_text(perception, report_with(damage)) is None
    # Enemy-chain damage (targets a party member) never counts as the actor's damage.
    enemy_hit = envelope("damage_applied", {"character_id": brix_id.value, "amount": 4})
    assert _episodic_text(perception, report_with(hit, damage, enemy_hit)) == (
        "Round 1: attacked Goblin and dealt 5 damage."
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/memory -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.memory'`.

- [ ] **Step 3: Implement `src/application/memory/`**

`src/application/memory/__init__.py`:

```python
"""Agent memory policy for the application layer (spec §3.3)."""
```

`src/application/memory/memory_service.py`:

```python
"""Memory policy: derive, embed, store, and retrieve one agent's memories (spec §3.3)."""

from __future__ import annotations

import asyncio
import uuid

from ai.memory.ports import EmbeddingGateway, MemoryRepository
from ai.memory.types import EmbeddingRequest, MemoryKind, MemoryRecord
from application.agents.perception import AgentPerception
from application.views import TurnReport

_RETRIEVAL_LIMIT = 5


class MemoryService:
    """Coordinates the embedding gateway and the memory repository for a game's agents."""

    def __init__(
        self,
        gateway: EmbeddingGateway,
        repository: MemoryRepository,
        *,
        model: str,
        retrieval_limit: int = _RETRIEVAL_LIMIT,
    ) -> None:
        self._gateway = gateway
        self._repository = repository
        self._model = model
        self._retrieval_limit = retrieval_limit

    def retrieve(
        self, game_id: str, perception: AgentPerception
    ) -> tuple[MemoryRecord, ...]:
        """Embed the situation line and return the agent's most relevant memories."""
        me = perception.self_view
        opponent_names = (
            ", ".join(opponent.name for opponent in perception.opponents) or "none"
        )
        query = (
            f"{me.name} the {me.character_class}; "
            f"round {perception.round_number}; opponents: {opponent_names}"
        )
        response = asyncio.run(
            self._gateway.embed(EmbeddingRequest(texts=(query,), model=self._model))
        )
        return self._repository.search(
            game_id, me.id, response.vectors[0], limit=self._retrieval_limit
        )

    def record_turn(
        self,
        game_id: str,
        perception: AgentPerception,
        turn_report: TurnReport,
        *,
        note: str | None = None,
    ) -> None:
        """Record this turn's episodic (events) and semantic (note) memories."""
        if not turn_report.accepted:
            return
        entries: list[tuple[MemoryKind, str]] = []
        episode = _episodic_text(perception, turn_report)
        if episode is not None:
            entries.append((MemoryKind.EPISODIC, episode))
        if note is not None:
            entries.append((MemoryKind.SEMANTIC, note))
        if not entries:
            return
        response = asyncio.run(
            self._gateway.embed(
                EmbeddingRequest(
                    texts=tuple(text for _, text in entries), model=self._model
                )
            )
        )
        for (kind, text), vector in zip(entries, response.vectors, strict=True):
            self._repository.append(
                MemoryRecord(
                    memory_id=uuid.uuid4().hex,
                    game_id=game_id,
                    agent_key=perception.self_view.id,
                    kind=kind,
                    text=text,
                    round_number=perception.round_number,
                    embedding=vector,
                )
            )


def _episodic_text(perception: AgentPerception, turn_report: TurnReport) -> str | None:
    """One deterministic line from the executed turn's domain events (spec Decision 6)."""
    names = {opponent.id: opponent.name for opponent in perception.opponents}
    names[perception.self_view.id] = perception.self_view.name
    attack: dict[str, object] | None = None
    target_id: str | None = None
    damage_total = 0
    defeated: set[str] = set()
    for envelope in turn_report.events:
        payload = envelope.payload
        if (
            envelope.event_type == "attack_resolved"
            and payload.get("attacker_id") == perception.self_view.id
        ):
            attack = payload
            target_id = str(payload.get("target_id"))
        elif envelope.event_type == "damage_applied":
            # Damage from the enemy chain targets party members; only damage to
            # this attack's target is attributable to the actor (spec Decision 6).
            if target_id is not None and str(payload.get("character_id")) == target_id:
                damage_total += int(str(payload.get("amount", 0)))
        elif envelope.event_type == "character_defeated":
            defeated.add(str(payload.get("character_id")))
    if attack is None or target_id is None:
        return None
    target = names.get(target_id, target_id)
    if attack.get("hit"):
        text = (
            f"Round {perception.round_number}: attacked {target} "
            f"and dealt {damage_total} damage"
        )
        if attack.get("critical"):
            text += " (critical)"
    else:
        text = f"Round {perception.round_number}: attacked {target} and missed"
    if target_id in defeated:
        text += f"; {target} fell"
    return text + "."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/memory -q`
Expected: PASS (10 tests).

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 343.

- [ ] **Step 6: Commit**

```bash
git add src/application/memory tests/application/memory
git commit -m "feat(application): add MemoryService with episodic derivation and retrieval

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: `OpenRouterModelGateway.embed()` — real embeddings

**Files:**
- Modify: `src/infrastructure/llm/openrouter/adapter.py`
- Modify: `src/infrastructure/llm/factory.py`
- Test: `tests/infrastructure/llm/test_openrouter_embed.py` (new)
- Test: `tests/integration/test_openrouter_live.py` (append 1 live test)

**Interfaces:**
- Consumes: `EmbeddingRequest`/`EmbeddingResponse` (Task 1); the adapter's existing `_post`/`_body`/`_cost`/`_latency_ms`/`_with_invocation` machinery.
- Produces: `OpenRouterModelGateway` now satisfies `EmbeddingGateway` structurally — `async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse`, POSTing `{base_url}/embeddings` with `{"model", "input": [texts]}`, parsing `data[].embedding` (rejecting count mismatches, malformed/non-numeric embeddings), usage from `usage.prompt_tokens` (output 0), cost via the existing pricing table, `operation="embed"`; every existing error mapping applies and failures carry an attached `LLMInvocation` (status `"error"` or `"timeout"`). Also `create_embedding_gateway(provider: str, *, api_key: str) -> EmbeddingGateway` in the factory (same `_PROVIDERS` lookup as `create_gateway`; the provider name is always a config value). Two internal refactors, both behavior-preserving: `_post(url, payload, timeout_seconds)` (URL and timeout become parameters; `_execute` passes `f"{self._base_url}/chat/completions"` and `request.timeout_seconds`) and `_with_invocation(model: str, operation: str, ...)` (takes the model string instead of the `ModelRequest`; both existing call sites pass `request.model`).

- [ ] **Step 1: Write the failing tests**

`tests/infrastructure/llm/test_openrouter_embed.py`:

```python
"""OpenRouterModelGateway.embed: OpenAI-compatible /embeddings mapping (spec §3.2)."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ai.memory.types import EmbeddingRequest
from ai.models.errors import (
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelUnavailableError,
)
from ai.models.profiles import ModelPricing
from infrastructure.llm.openrouter.adapter import OpenRouterModelGateway

_EMBED_BODY: dict[str, Any] = {
    "id": "emb-1",
    "model": "openai/text-embedding-3-small",
    "data": [
        {"index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"index": 1, "embedding": [0.4, 0.5]},
    ],
    "usage": {"prompt_tokens": 9},
}


def _gateway(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    pricing: dict[str, ModelPricing] | None = None,
) -> OpenRouterModelGateway:
    return OpenRouterModelGateway(
        "test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        pricing=pricing,
    )


def _request(**overrides: Any) -> EmbeddingRequest:
    values: dict[str, Any] = {
        "texts": ("Brix attacks.", "Goblin falls."),
        "model": "openai/text-embedding-3-small",
    }
    values.update(overrides)
    return EmbeddingRequest(**values)


def test_embed_posts_the_openai_compatible_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_EMBED_BODY)

    response = asyncio.run(_gateway(handler).embed(_request()))

    assert captured["url"].endswith("/embeddings")
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"] == {
        "model": "openai/text-embedding-3-small",
        "input": ["Brix attacks.", "Goblin falls."],
    }
    assert response.vectors == ((0.1, 0.2, 0.3), (0.4, 0.5))


def test_embed_maps_usage_invocation_and_cost() -> None:
    pricing = {
        "openai/text-embedding-3-small": ModelPricing(
            input_per_million_usd=0.02, output_per_million_usd=0.0
        )
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_EMBED_BODY)

    response = asyncio.run(_gateway(handler, pricing=pricing).embed(_request()))

    assert response.usage.input_tokens == 9
    assert response.usage.output_tokens == 0
    assert response.invocation.provider == "openrouter"
    assert response.invocation.model == "openai/text-embedding-3-small"
    assert response.invocation.operation == "embed"
    assert response.invocation.status == "ok"
    assert response.invocation.input_tokens == 9
    assert response.invocation.output_tokens == 0
    assert response.invocation.estimated_cost_usd == pytest.approx(9 / 1_000_000 * 0.02)
    assert response.invocation.request_id


def test_embed_rejects_a_count_mismatch() -> None:
    body = {**_EMBED_BODY, "data": _EMBED_BODY["data"][:1]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(ModelInvalidResponseError, match="embeddings for 2"):
        asyncio.run(_gateway(handler).embed(_request()))


def test_embed_rejects_malformed_embeddings() -> None:
    non_numeric = {
        **_EMBED_BODY,
        "data": [
            {"index": 0, "embedding": ["x", None]},
            {"index": 1, "embedding": [0.1]},
        ],
    }
    not_an_object = {**_EMBED_BODY, "data": ["nope", "nope"]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=non_numeric)

    with pytest.raises(ModelInvalidResponseError, match="non-numeric"):
        asyncio.run(_gateway(handler).embed(_request()))

    def bad_shape(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=not_an_object)

    with pytest.raises(ModelInvalidResponseError, match="malformed"):
        asyncio.run(_gateway(bad_shape).embed(_request()))


def test_embed_maps_error_statuses_and_carries_the_invocation() -> None:
    def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": "slow down"}, headers={"retry-after": "7"}
        )

    with pytest.raises(ModelRateLimitedError) as limited:
        asyncio.run(_gateway(rate_limited).embed(_request()))
    assert limited.value.retry_after_seconds == 7.0
    assert limited.value.invocation is not None
    assert limited.value.invocation.operation == "embed"
    assert limited.value.invocation.status == "error"
    assert limited.value.invocation.error_kind == "rate_limited"

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    with pytest.raises(ModelUnavailableError):
        asyncio.run(_gateway(unavailable).embed(_request()))


def test_embed_rejects_a_non_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(ModelInvalidResponseError, match="non-JSON"):
        asyncio.run(_gateway(handler).embed(_request()))
```

Then append to `tests/integration/test_openrouter_live.py` (imports to add: `from ai.memory.types import EmbeddingRequest` and `from infrastructure.llm import create_embedding_gateway` — replacing the single-import `from infrastructure.llm import create_gateway` line):

```python
def test_openrouter_live_embed() -> None:
    gateway = create_embedding_gateway(
        "openrouter", api_key=os.environ["OPENROUTER_API_KEY"]
    )
    request = EmbeddingRequest(
        texts=("Brix strikes the goblin.",), model="openai/text-embedding-3-small"
    )
    response = asyncio.run(gateway.embed(request))

    assert len(response.vectors) == 1
    assert len(response.vectors[0]) == 1536
    assert response.invocation.provider == "openrouter"
    assert response.invocation.operation == "embed"
    assert response.invocation.status == "ok"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm/test_openrouter_embed.py -q`
Expected: FAIL with `AttributeError: ... 'OpenRouterModelGateway' object has no attribute 'embed'`.

- [ ] **Step 3: Modify the adapter**

In `src/infrastructure/llm/openrouter/adapter.py`:

(a) Add the import (before the `ai.models.errors` import — `ai.memory` sorts before `ai.models`):

```python
from ai.memory.types import EmbeddingRequest, EmbeddingResponse
```

(b) Change `_with_invocation` to take the model string (used by embed too):

```python
    def _with_invocation(
        self,
        model: str,
        operation: str,
        started: float,
        request_id: str,
        exc: ModelError,
    ) -> ModelError:
        status = "timeout" if isinstance(exc, ModelTimeoutError) else "error"
        exc.invocation = LLMInvocation(
            provider="openrouter",
            model=model,
            operation=operation,
            status=status,
            error_kind=_error_kind(exc),
            latency_ms=self._latency_ms(started),
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            request_id=request_id,
        )
        return exc
```

and update its two existing call sites to pass `request.model` as the first argument:

```python
            raise self._with_invocation(
                request.model, "generate", started, request_id, exc
            ) from exc
```
```python
            raise self._with_invocation(
                request.model, "generate_structured", started, request_id, exc
            ) from exc
```

(c) Change `_post` to take url and timeout, and update `_execute`'s call:

```python
    async def _post(
        self, url: str, payload: dict[str, Any], timeout_seconds: float
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._app_url is not None:
            headers["HTTP-Referer"] = self._app_url
        if self._app_title is not None:
            headers["X-Title"] = self._app_title
        timeout = httpx.Timeout(timeout_seconds)
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient() as client:
            return await client.post(url, json=payload, headers=headers, timeout=timeout)
```

```python
        payload = self._payload(request, operation)
        try:
            response = await self._post(
                f"{self._base_url}/chat/completions",
                payload,
                request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
```

(d) Insert `embed` after `generate_structured`, and the two helpers after `_execute`:

```python
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed a batch of texts via the OpenAI-compatible /embeddings endpoint."""
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        try:
            body, vectors = await self._execute_embeddings(request)
        except ModelError as exc:
            raise self._with_invocation(
                request.model, "embed", started, request_id, exc
            ) from exc
        usage = Usage(
            input_tokens=int((body.get("usage") or {}).get("prompt_tokens", 0)),
            output_tokens=0,
        )
        model = str(body.get("model", request.model))
        invocation = LLMInvocation(
            provider="openrouter",
            model=model,
            operation="embed",
            status="ok",
            error_kind=None,
            latency_ms=self._latency_ms(started),
            input_tokens=usage.input_tokens,
            output_tokens=0,
            estimated_cost_usd=self._cost(model, usage),
            request_id=request_id,
        )
        return EmbeddingResponse(vectors=vectors, usage=usage, invocation=invocation)
```

```python
    async def _execute_embeddings(
        self, request: EmbeddingRequest
    ) -> tuple[dict[str, Any], tuple[tuple[float, ...], ...]]:
        payload = {"model": request.model, "input": list(request.texts)}
        try:
            response = await self._post(
                f"{self._base_url}/embeddings", payload, request.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"OpenRouter transport error: {exc}") from exc
        body = self._body(response)
        return body, self._embedding_vectors(body, len(request.texts))

    @staticmethod
    def _embedding_vectors(
        body: dict[str, Any], expected: int
    ) -> tuple[tuple[float, ...], ...]:
        data = body.get("data")
        if not isinstance(data, list):
            raise ModelInvalidResponseError("OpenRouter returned no embedding data")
        if len(data) != expected:
            raise ModelInvalidResponseError(
                f"OpenRouter returned {len(data)} embeddings for {expected} input(s)"
            )
        vectors: list[tuple[float, ...]] = []
        for entry in data:
            raw = entry.get("embedding") if isinstance(entry, dict) else None
            if not isinstance(raw, list) or not raw:
                raise ModelInvalidResponseError(
                    "OpenRouter returned a malformed embedding"
                )
            try:
                vectors.append(tuple(float(value) for value in raw))
            except (TypeError, ValueError) as exc:
                raise ModelInvalidResponseError(
                    "OpenRouter returned a non-numeric embedding"
                ) from exc
        return tuple(vectors)
```

(e) In `src/infrastructure/llm/factory.py`, add the import `from ai.memory.ports import EmbeddingGateway` (after the existing `ai.models.errors` import — `ai.memory` sorts first) and the factory function:

```python
def create_embedding_gateway(provider: str, *, api_key: str) -> EmbeddingGateway:
    """Build the embedding gateway registered for *provider* (Plan 6 carve-out)."""
    adapter_class = _PROVIDERS.get(provider)
    if adapter_class is None:
        raise UnknownProviderError(
            f"no embedding gateway registered for provider {provider!r}"
        )
    return adapter_class(api_key)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/llm -q`
Expected: PASS — all pre-existing adapter tests still green (the refactors are behavior-preserving) plus the 6 new embed tests.

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 349 (plus 1 skipped live test).

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/llm/openrouter/adapter.py src/infrastructure/llm/factory.py tests/infrastructure/llm/test_openrouter_embed.py tests/integration/test_openrouter_live.py
git commit -m "feat(infrastructure): add OpenRouter embeddings support

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Migration `002_agent_memories.sql` + `PgvectorMemoryRepository`

**Files:**
- Create: `src/infrastructure/persistence/postgres/migrations/002_agent_memories.sql`
- Create: `src/infrastructure/memory/pgvector_repository.py`
- Test: `tests/infrastructure/memory/test_pgvector_repository.py`

**Interfaces:**
- Consumes: the pgserver-backed `postgres_url` session fixture in `tests/conftest.py` (applies all migrations automatically); `connect()` from `infrastructure.persistence.postgres.connection` (autocommit, `dict_row`, returns `psycopg.Connection[dict[str, Any]]`); `PersistenceError` from `domain.common.errors`.
- Produces: table `agent_memories (memory_id UUID PK, game_id UUID → games ON DELETE CASCADE, agent_key TEXT, kind TEXT, text TEXT, round_number INTEGER, embedding VECTOR NOT NULL, created_at TIMESTAMPTZ)` + index `(game_id, agent_key)`; `PgvectorMemoryRepository(connection)` — satisfies `MemoryRepository` structurally, same append/search contract as Task 3 (duplicate no-op via existence check inside a transaction; `<=>` cosine ordering; `limit <= 0` → `()`). The embedding column is sent as the pgvector text literal `"[1,0.5,0.25]"` cast `::vector`; rows come back as text (psycopg has no vector codec) and are parsed.

- [ ] **Step 1: Write the failing tests**

`tests/infrastructure/memory/test_pgvector_repository.py`:

```python
"""PgvectorMemoryRepository against real PostgreSQL + pgvector (offline via pgserver)."""

import uuid

from ai.memory.types import MemoryKind, MemoryRecord
from infrastructure.memory.pgvector_repository import PgvectorMemoryRepository
from infrastructure.persistence.postgres.connection import connect


def _record(
    game_id: str,
    agent_key: str,
    text: str,
    embedding: tuple[float, ...],
    *,
    kind: MemoryKind = MemoryKind.EPISODIC,
    round_number: int | None = 1,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=uuid.uuid4().hex,
        game_id=game_id,
        agent_key=agent_key,
        kind=kind,
        text=text,
        round_number=round_number,
        embedding=embedding,
    )


def test_migration_creates_the_table_and_the_vector_extension(postgres_url: str) -> None:
    connection = connect(postgres_url)
    extension = connection.execute(
        "SELECT extname FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    table = connection.execute(
        "SELECT to_regclass('agent_memories') AS reg"
    ).fetchone()
    connection.close()

    assert extension is not None
    assert table is not None
    assert table["reg"] == "agent_memories"


def test_append_then_search_orders_by_cosine_similarity(postgres_url: str) -> None:
    game_id = uuid.uuid4().hex
    connection = connect(postgres_url)
    repo = PgvectorMemoryRepository(connection)
    repo.append(_record(game_id, "brix", "near", (1.0, 0.0, 0.0)))
    repo.append(_record(game_id, "brix", "far", (0.0, 1.0, 0.0)))

    results = repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=5)
    connection.close()

    assert [record.text for record in results] == ["near", "far"]


def test_search_scopes_to_game_and_agent(postgres_url: str) -> None:
    game_id = uuid.uuid4().hex
    connection = connect(postgres_url)
    repo = PgvectorMemoryRepository(connection)
    repo.append(_record(game_id, "brix", "mine", (1.0, 0.0, 0.0)))
    repo.append(_record(game_id, "mira", "other agent", (1.0, 0.0, 0.0)))
    repo.append(_record(uuid.uuid4().hex, "brix", "other game", (1.0, 0.0, 0.0)))

    results = repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=5)
    connection.close()

    assert [record.text for record in results] == ["mine"]


def test_append_exact_duplicate_is_a_noop(postgres_url: str) -> None:
    game_id = uuid.uuid4().hex
    connection = connect(postgres_url)
    repo = PgvectorMemoryRepository(connection)
    repo.append(
        _record(game_id, "brix", "same text", (1.0, 0.0, 0.0), kind=MemoryKind.SEMANTIC)
    )
    repo.append(
        _record(game_id, "brix", "same text", (0.0, 1.0, 0.0), kind=MemoryKind.SEMANTIC)
    )

    results = repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=5)
    connection.close()

    assert len(results) == 1
    assert results[0].embedding == (1.0, 0.0, 0.0)  # first write wins


def test_search_empty_scope_and_non_positive_limit_return_empty(
    postgres_url: str,
) -> None:
    game_id = uuid.uuid4().hex
    connection = connect(postgres_url)
    repo = PgvectorMemoryRepository(connection)
    repo.append(_record(game_id, "brix", "mine", (1.0, 0.0, 0.0)))

    assert repo.search(uuid.uuid4().hex, "brix", (1.0, 0.0, 0.0), limit=5) == ()
    assert repo.search(game_id, "nobody", (1.0, 0.0, 0.0), limit=5) == ()
    assert repo.search(game_id, "brix", (1.0, 0.0, 0.0), limit=0) == ()
    connection.close()


def test_search_roundtrips_every_field(postgres_url: str) -> None:
    game_id = uuid.uuid4().hex
    connection = connect(postgres_url)
    repo = PgvectorMemoryRepository(connection)
    repo.append(
        _record(
            game_id,
            "brix",
            "note",
            (1.0, 0.5, 0.0),  # float32-exact values
            kind=MemoryKind.SEMANTIC,
            round_number=3,
        )
    )

    results = repo.search(game_id, "brix", (1.0, 0.5, 0.0), limit=5)
    connection.close()

    assert len(results) == 1
    record = results[0]
    assert len(record.memory_id) == 32  # uuid hex round-trips through ::uuid
    assert str(game_id) == record.game_id or len(record.game_id) == 32
    assert record.agent_key == "brix"
    assert record.kind is MemoryKind.SEMANTIC
    assert record.text == "note"
    assert record.round_number == 3
    assert record.embedding == (1.0, 0.5, 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/memory/test_pgvector_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'infrastructure.memory.pgvector_repository'`.

- [ ] **Step 3: Implement the migration and the repository**

`src/infrastructure/persistence/postgres/migrations/002_agent_memories.sql`:

```sql
-- 002_agent_memories.sql — agent memory store for the Plan 6 memory platform.
-- Untyped vector column (no typmod): switching embedding models never
-- requires a migration; dimension mismatches surface at query time.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE agent_memories (
    memory_id    UUID PRIMARY KEY,
    game_id      UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    agent_key    TEXT NOT NULL,
    kind         TEXT NOT NULL,
    text         TEXT NOT NULL,
    round_number INTEGER,
    embedding    VECTOR NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX agent_memories_scope_idx ON agent_memories (game_id, agent_key);

-- Append-only by construction: no code path issues UPDATE or DELETE here.
```

`src/infrastructure/memory/pgvector_repository.py`:

```python
"""pgvector-backed memory repository: cosine search over agent memories (spec §3.2)."""

from __future__ import annotations

from typing import Any

import psycopg

from ai.memory.types import MemoryKind, MemoryRecord
from domain.common.errors import PersistenceError


def _vector_literal(vector: tuple[float, ...]) -> str:
    """pgvector's text format: '[1,0.5,0.25]' — cast with ::vector in the SQL."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def _embedding_from_row(raw: object) -> tuple[float, ...]:
    """psycopg sees the untyped vector column as text ('[1,0.5,0.25]') or a list."""
    if isinstance(raw, str):
        stripped = raw.strip().strip("[]")
        if not stripped:
            return ()
        return tuple(float(part) for part in stripped.split(","))
    if isinstance(raw, (list, tuple)):
        return tuple(float(value) for value in raw)
    raise PersistenceError(f"unexpected embedding column type: {type(raw)!r}")


class PgvectorMemoryRepository:
    """Cosine search via pgvector's <=> operator; exact-duplicate appends are no-ops."""

    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection

    def append(self, record: MemoryRecord) -> None:
        try:
            with self._connection.transaction():
                duplicate = self._connection.execute(
                    """
                    SELECT 1 FROM agent_memories
                    WHERE game_id = %s::uuid AND agent_key = %s
                      AND kind = %s AND text = %s
                    """,
                    (
                        record.game_id,
                        record.agent_key,
                        record.kind.value,
                        record.text,
                    ),
                ).fetchone()
                if duplicate is not None:
                    return
                self._connection.execute(
                    """
                    INSERT INTO agent_memories
                        (memory_id, game_id, agent_key, kind, text, round_number,
                         embedding)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::vector)
                    """,
                    (
                        record.memory_id,
                        record.game_id,
                        record.agent_key,
                        record.kind.value,
                        record.text,
                        record.round_number,
                        _vector_literal(record.embedding),
                    ),
                )
        except psycopg.Error as error:
            raise PersistenceError(f"could not append memory: {error}") from error

    def search(
        self,
        game_id: str,
        agent_key: str,
        query: tuple[float, ...],
        limit: int,
    ) -> tuple[MemoryRecord, ...]:
        if limit <= 0:
            return ()
        try:
            rows = self._connection.execute(
                """
                SELECT memory_id, game_id, agent_key, kind, text, round_number,
                       embedding
                FROM agent_memories
                WHERE game_id = %s::uuid AND agent_key = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (game_id, agent_key, _vector_literal(query), limit),
            ).fetchall()
        except psycopg.Error as error:
            raise PersistenceError(f"could not search memories: {error}") from error
        return tuple(
            MemoryRecord(
                memory_id=str(row["memory_id"]),
                game_id=str(row["game_id"]),
                agent_key=row["agent_key"],
                kind=MemoryKind(row["kind"]),
                text=row["text"],
                round_number=row["round_number"],
                embedding=_embedding_from_row(row["embedding"]),
            )
            for row in rows
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/memory -q`
Expected: PASS (13 tests in the directory: 7 in-memory + 6 pgvector).

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 355 (pgvector tests run offline against pgserver).

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/persistence/postgres/migrations/002_agent_memories.sql src/infrastructure/memory/pgvector_repository.py tests/infrastructure/memory/test_pgvector_repository.py
git commit -m "feat(infrastructure): add pgvector memory repository and migration

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Wire memory into `AgentTurnService`

**Files:**
- Modify: `src/application/agents/agent_turn_service.py`
- Test: `tests/application/agents/test_agent_turn_service.py` (append helpers + 6 tests)

**Interfaces:**
- Consumes: everything from Tasks 1–5 (`MemoryService`, `MemoryRecord`, `ModelError`, `PersistenceError`).
- Produces: `AgentTurnService(..., *, max_action_retries=None, board=None, memory: MemoryService | None = None)`; `AgentTurnReport` gains `memory_retrieved: int = 0`. `take_turn` hoists `get_view` + `build_perception` out of the retry loop (behavior-preserving: rejected actions never mutate state, §28) and retrieves memories once per turn; every `build_user_prompt` call passes `memories=memories`; after an accepted model turn it records `note=decision.memory_note`; after an accepted fallback turn it records `note=None` (episodic only). Both memory calls swallow only `ModelError` (attaching `error.invocation` to the report's invocations when present) and `PersistenceError`. `memory=None` reproduces Plan 5 behavior exactly — all 10 existing tests must stay green unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/application/agents/test_agent_turn_service.py`, add imports (merge `ModelRequestError` into the existing `ai.models.errors` import):

```python
import asyncio

from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.ports import EmbeddingGateway
from ai.memory.types import EmbeddingRequest, MemoryKind, MemoryRecord
from application.agents.perception import AgentPerception, OpponentBrief
from application.memory.memory_service import MemoryService
from infrastructure.memory.in_memory import InMemoryMemoryRepository
```

Change `_agent_service` to accept and forward memory:

```python
def _agent_service(
    game_service: GameService,
    gateway: FakeModelGateway,
    *,
    max_action_retries: int = 2,
    board: PartyMessageBoard | None = None,
    memory: MemoryService | None = None,
) -> AgentTurnService:
    runtime = AgentRuntime(gateway, RetryPolicy(max_attempts=3))
    agent_profiles = AgentProfileCatalog(
        max_action_retries=max_action_retries,
        agents={"brix": _BRIX},
    )
    return AgentTurnService(
        game_service, runtime, _MODEL_CATALOG, agent_profiles, board=board, memory=memory
    )
```

Add the helpers before the new tests:

```python
class _FailingEmbeddingGateway:
    """Embedder that always fails — memory must never gate the turn (spec §2.8)."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise ModelRequestError("embeddings are down")


def _memory_service(
    gateway: EmbeddingGateway | None = None,
) -> tuple[MemoryService, InMemoryMemoryRepository]:
    repo = InMemoryMemoryRepository()
    embedder = gateway if gateway is not None else DeterministicEmbeddingGateway()
    return MemoryService(embedder, repo, model="test-model"), repo


def _retrieval_perception(
    game_service: GameService, game_id: GameId, actor_id: str
) -> AgentPerception:
    """A perception for retrieval assertions — the turn is over, so build it manually."""
    view = game_service.get_view(game_id)
    me = next(member for member in (*view.party, *view.enemies) if member.id == actor_id)
    opponents = tuple(
        OpponentBrief(id=enemy.id, name=enemy.name, is_defeated=enemy.is_defeated)
        for enemy in view.enemies
    )
    combat = view.combat
    return AgentPerception(
        round_number=combat.round_number if combat else 1,
        active_actor_id=actor_id,
        self_view=me,
        opponents=opponents,
        initiative_order=(
            tuple(entry.name for entry in combat.initiative_order) if combat else ()
        ),
    )
```

(`EmbeddingResponse` must also join the `ai.memory.types` import above — `_FailingEmbeddingGateway.embed` returns it in its signature.)

The tests:

```python
def test_accepted_model_turn_records_an_episodic_memory() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    memory, _repo = _memory_service()
    service = _agent_service(game_service, fake, memory=memory)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    memories = memory.retrieve(
        str(game_id), _retrieval_perception(game_service, game_id, brix_id.value)
    )
    episodic = [record for record in memories if record.kind is MemoryKind.EPISODIC]
    assert len(episodic) == 1
    assert episodic[0].text.startswith("Round 1: attacked Goblin and ")


def test_accepted_model_turn_records_the_semantic_note() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {
            "action_type": "attack",
            "target_id": goblin_id.value,
            "public_message": "I strike.",
            "memory_note": "The goblin bleeds — finish it.",
        }
    )
    memory, _repo = _memory_service()
    service = _agent_service(game_service, fake, memory=memory)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    memories = memory.retrieve(
        str(game_id), _retrieval_perception(game_service, game_id, brix_id.value)
    )
    assert any(
        record.kind is MemoryKind.SEMANTIC
        and record.text == "The goblin bleeds — finish it."
        for record in memories
    )


def test_retrieved_memories_render_into_the_prompt_and_count() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    text = "Brix watches the Goblin closely."
    vector = asyncio.run(
        DeterministicEmbeddingGateway().embed(
            EmbeddingRequest(texts=(text,), model="test-model")
        )
    ).vectors[0]
    memory, repo = _memory_service()
    repo.append(
        MemoryRecord(
            memory_id="seed-1",
            game_id=str(game_id),
            agent_key=brix_id.value,
            kind=MemoryKind.SEMANTIC,
            text=text,
            round_number=1,
            embedding=vector,
        )
    )
    fake = _CapturingFake()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    service = _agent_service(game_service, fake, memory=memory)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    assert report.memory_retrieved == 1
    user_content = fake.requests[0].messages[-1].content
    assert "Memories:" in user_content
    assert f"- [semantic] {text}" in user_content


def test_fallback_turn_records_episodic_memory_only() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(6):  # 2 decision attempts x 3 transport attempts
        fake.enqueue_error(ModelTimeoutError("boom"))
    memory, _repo = _memory_service()
    service = _agent_service(game_service, fake, max_action_retries=1, memory=memory)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    assert report.accepted is True
    memories = memory.retrieve(
        str(game_id), _retrieval_perception(game_service, game_id, brix_id.value)
    )
    assert len(memories) == 1
    assert memories[0].kind is MemoryKind.EPISODIC


def test_rejected_attempts_record_no_semantic_memory() -> None:
    game_service = _game_service()
    game_id, brix_id, _goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    for _ in range(2):  # max_action_retries=1 -> 2 invalid decision attempts
        fake.enqueue_structured(
            {
                "action_type": "attack",
                "target_id": "nobody",
                "public_message": "Who?",
                "memory_note": "should never persist",
            }
        )
    memory, _repo = _memory_service()
    service = _agent_service(game_service, fake, max_action_retries=1, memory=memory)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.proposal_source == "fallback"
    memories = memory.retrieve(
        str(game_id), _retrieval_perception(game_service, game_id, brix_id.value)
    )
    assert len(memories) == 1  # the fallback attack's episodic memory
    assert all(record.kind is MemoryKind.EPISODIC for record in memories)


def test_embedding_failure_never_fails_the_turn() -> None:
    game_service = _game_service()
    game_id, brix_id, goblin_id = _party_with_brix_first(game_service)
    fake = FakeModelGateway()
    fake.enqueue_structured(
        {"action_type": "attack", "target_id": goblin_id.value, "public_message": "I strike."}
    )
    memory, _repo = _memory_service(_FailingEmbeddingGateway())
    service = _agent_service(game_service, fake, memory=memory)
    service.register(brix_id, _BRIX)

    report = service.take_turn(game_id, brix_id)

    assert report.accepted is True
    assert report.memory_retrieved == 0
    assert len(report.invocations) == 1  # only the decision call; retrieval degraded
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/application/agents/test_agent_turn_service.py -q`
Expected: FAIL — `TypeError: AgentTurnService.__init__() got an unexpected keyword argument 'memory'`.

- [ ] **Step 3: Modify `src/application/agents/agent_turn_service.py`**

(a) Imports — add `from ai.memory.types import MemoryRecord` and `from ai.models.errors import ModelError` (after `from ai.agents.runtime import AgentRuntime`, `ai.memory` sorts before `ai.models`), add `from application.memory.memory_service import MemoryService` (after `application.game_service`), and add `from domain.common.errors import PersistenceError` (before `from domain.common.ids import ...`).

(b) `AgentTurnReport` gains the field after `party_message`:

```python
    party_message: str | None = None
    memory_retrieved: int = 0
```

(c) `__init__` gains the kwarg and assignment:

```python
        board: PartyMessageBoard | None = None,
        memory: MemoryService | None = None,
    ) -> None:
```
with `self._memory = memory` alongside the other assignments (before `self._agents`).

(d) Replace `take_turn`'s body from the loop start through the fallback call — the view/perception build moves OUT of the loop and memories are threaded through:

```python
    def take_turn(self, game_id: GameId, actor_id: CharacterId) -> AgentTurnReport:
        profile = self._agents.get(actor_id.value)
        if profile is None:
            raise AgentNotRegisteredError(actor_id.value)

        agent = CharacterAgent(profile)
        model_profile = self._catalog.get(profile.model_profile)
        invocations: list[LLMInvocation] = []
        rejection_reasons: list[str] = []
        rejection: str | None = None

        # Rejected actions never mutate game state (§28), so one perception serves
        # every attempt; hoisting it also makes memory retrieval once-per-turn.
        view = self._game_service.get_view(game_id)
        perception = build_perception(view, actor_id.value)
        memories = self._retrieve_memories(game_id, perception, invocations)

        for attempt in range(1, self._max_action_retries + 2):
            try:
                response = self._runtime.decide_structured(
                    profile=model_profile,
                    system=agent.build_system_prompt(),
                    user=agent.build_user_prompt(
                        perception,
                        rejection=rejection,
                        party_messages=self._board.recent(_PARTY_CHATTER_LIMIT),
                        memories=memories,
                    ),
                    schema=ATTACK_DECISION_SCHEMA,
                )
                invocations.append(response.invocation)
                decision = agent.map_decision(response.data, perception)
            except AgentRuntimeMisconfiguredError:
                raise
            except AgentRuntimeError as error:
                if error.last_invocation is not None:
                    invocations.append(error.last_invocation)
                rejection = f"model failure: {error}"
                rejection_reasons.append(rejection)
                continue
            except InvalidAgentDecisionError as error:
                rejection = str(error)
                rejection_reasons.append(rejection)
                continue

            turn_report = self._submit(game_id, actor_id, decision)
            if turn_report.accepted:
                if decision.party_message is not None:
                    self._board.post(
                        PartyMessage(
                            actor_name=perception.self_view.name,
                            text=decision.party_message,
                            round_number=perception.round_number,
                        )
                    )
                self._record_memories(
                    game_id, perception, turn_report, decision.memory_note, invocations
                )
                return AgentTurnReport(
                    actor_id=actor_id.value,
                    actor_name=perception.self_view.name,
                    accepted=True,
                    proposal_source="model",
                    action_attempts=attempt,
                    rejection_reasons=tuple(rejection_reasons),
                    fallback_reason=None,
                    public_message=decision.public_message,
                    invocations=tuple(invocations),
                    turn_report=turn_report,
                    party_message=decision.party_message,
                    memory_retrieved=len(memories),
                )
            rejection = turn_report.reason or "action rejected by the rules engine"
            rejection_reasons.append(rejection)

        return self._fallback(
            game_id,
            actor_id,
            perception,
            memories,
            invocations,
            tuple(rejection_reasons),
        )
```

(The old `perception: AgentPerception | None = None` local and the trailing `assert perception is not None` are gone.)

(e) `_fallback` takes the perception and memories, records after the accepted fallback attack, and reports the count:

```python
    def _fallback(
        self,
        game_id: GameId,
        actor_id: CharacterId,
        perception: AgentPerception,
        memories: tuple[MemoryRecord, ...],
        invocations: list[LLMInvocation],
        rejection_reasons: tuple[str, ...],
    ) -> AgentTurnReport:
        view = self._game_service.get_view(game_id)
        target_id = first_living_opponent(view, actor_id.value)
        if target_id is None:
            raise AgentNotInCombatError(
                f"character {actor_id.value} has no living opponent to attack"
            )
        detail = "; ".join(rejection_reasons) if rejection_reasons else "no model decision"
        turn_report = self._game_service.submit_action(
            SubmitActionCommand(
                game_id=game_id,
                actor_id=actor_id,
                action_type="attack",
                target_id=CharacterId(target_id),
            )
        )
        self._record_memories(game_id, perception, turn_report, None, invocations)
        return AgentTurnReport(
            actor_id=actor_id.value,
            actor_name=perception.self_view.name,
            accepted=turn_report.accepted,
            proposal_source="fallback",
            action_attempts=self._max_action_retries + 1,
            rejection_reasons=rejection_reasons,
            fallback_reason=f"decision budget exhausted ({detail})",
            public_message=None,
            invocations=tuple(invocations),
            turn_report=turn_report,
            party_message=None,
            memory_retrieved=len(memories),
        )
```

(f) Add the two private memory helpers at the end of the class:

```python
    def _retrieve_memories(
        self,
        game_id: GameId,
        perception: AgentPerception,
        invocations: list[LLMInvocation],
    ) -> tuple[MemoryRecord, ...]:
        """Memory never gates a turn (spec §2.8): failures degrade to no memories."""
        if self._memory is None:
            return ()
        try:
            return self._memory.retrieve(str(game_id), perception)
        except ModelError as error:
            if error.invocation is not None:
                invocations.append(error.invocation)
            return ()
        except PersistenceError:
            return ()

    def _record_memories(
        self,
        game_id: GameId,
        perception: AgentPerception,
        turn_report: TurnReport,
        note: str | None,
        invocations: list[LLMInvocation],
    ) -> None:
        """Recording never revisits an accepted action (spec §2.8): failures drop the write."""
        if self._memory is None:
            return
        try:
            self._memory.record_turn(str(game_id), perception, turn_report, note=note)
        except ModelError as error:
            if error.invocation is not None:
                invocations.append(error.invocation)
        except PersistenceError:
            return
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/application/agents -q`
Expected: PASS — all 10 pre-existing turn-service tests unchanged, plus the 6 new ones.

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 361.

- [ ] **Step 6: Commit**

```bash
git add src/application/agents/agent_turn_service.py tests/application/agents/test_agent_turn_service.py
git commit -m "feat(application): wire memory into the agent turn loop

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: CLI wiring, the embedding carve-out in config, factory, README

**Files:**
- Modify: `src/interfaces/cli/app.py`
- Modify: `config/llm.toml`
- Modify: `tests/ai/models/test_profiles.py` (modify 1 test, add 1 test)
- Modify: `README.md` (append a section)

**Interfaces:**
- Consumes: everything from Tasks 1–8, including `create_embedding_gateway(provider, *, api_key)` from Task 6's factory (the provider name comes from the shipped config — interfaces never name a provider).
- Produces: the CLI mode matrix (orthogonal wiring — embedder by agent mode, store by `--db`): `--agent llm` → `OpenRouterModelGateway` + real embeddings, `--agent fake` → `DeterministicEmbeddingGateway` (offline); `--db memory` → `InMemoryMemoryRepository`, `--db postgres` → `PgvectorMemoryRepository(connect(DATABASE_URL))` (a second connection owned by the memory repo — the CLI process needs no pooling); `--agent off` → no memory at all. `_wire_party` constructs the `MemoryService` with the shipped `[profiles.embedding]` profile and passes it to `AgentTurnService`; the fake-mode scripted decision gains `"memory_note": "The orc hits hard; stay at range."` so the offline demo exercises the full record→retrieve path.

- [ ] **Step 1: Write the failing test**

In `tests/ai/models/test_profiles.py`, replace `test_shipped_config_has_six_cheap_profiles` and add the new test (both shown in full):

```python
def test_shipped_config_has_six_cheap_profiles() -> None:
    config = Path(__file__).parents[3] / "config" / "llm.toml"
    catalog = load_model_profiles(config)
    assert catalog.default_provider == "openrouter"
    assert set(catalog.profiles) == {
        "gm",
        "player",
        "cheap",
        "reasoning",
        "creative",
        "embedding",
    }
    for name, profile in catalog.profiles.items():
        if name == "embedding":
            continue  # the one sanctioned carve-out (Plan 6, user decision 2026-09-06)
        assert profile.model == "z-ai/glm-5.3-flash"
    assert set(catalog.pricing) == {
        "z-ai/glm-5.3-flash",
        "z-ai/glm-5.2",
        "openai/text-embedding-3-small",
    }


def test_shipped_config_embedding_profile_is_the_sanctioned_carve_out() -> None:
    config = Path(__file__).parents[3] / "config" / "llm.toml"
    catalog = load_model_profiles(config)
    embedding = catalog.get("embedding")
    assert embedding.provider == "openrouter"
    assert embedding.model == "openai/text-embedding-3-small"
    assert catalog.pricing["openai/text-embedding-3-small"] == ModelPricing(
        input_per_million_usd=0.02, output_per_million_usd=0.0
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/ai/models/test_profiles.py -q`
Expected: FAIL — the shipped `llm.toml` still points `[profiles.embedding]` at `z-ai/glm-5.3-flash` and has no text-embedding pricing entry.

- [ ] **Step 3: Implement the config, factory, and CLI wiring**

(a) `config/llm.toml` — replace the header comment block:

```toml
# Model profiles for the Agentic Conclave model gateway (Plan 3).
# No secrets here: the OpenRouter key comes from the OPENROUTER_API_KEY env var.
# Until the final version, ALL chat profiles use the cheap model (user directive,
# 2026-09-04); upgrading a profile is a one-line config edit.
# Carve-out (explicit user decision 2026-09-06): [profiles.embedding] uses
# openai/text-embedding-3-small via OpenRouter's embeddings endpoint — glm-5.3-flash
# is a chat model and cannot produce embeddings. The deterministic embedder covers
# offline runs, so no key is required unless --agent llm is used.
```

replace the embedding profile:

```toml
[profiles.embedding]  # Plan 6 agent-memory embeddings (OpenAI-compatible /embeddings)
provider = "openrouter"
model = "openai/text-embedding-3-small"
```

and append the pricing entry after the `z-ai/glm-5.2` block:

```toml
[pricing."openai/text-embedding-3-small"]  # verified 2026-09-06; USD per million tokens
input_per_million_usd = 0.02
output_per_million_usd = 0.0
```

(b) `src/interfaces/cli/app.py` — imports: add

```python
from ai.memory.fake import DeterministicEmbeddingGateway
from ai.memory.ports import EmbeddingGateway, MemoryRepository
```

(after `from ai.agents.runtime import AgentRuntime`), add

```python
from application.memory.memory_service import MemoryService
```

(after `from application.game_service import GameService`), and replace the factory import line with

```python
from infrastructure.llm import create_embedding_gateway, create_gateway
from infrastructure.memory.in_memory import InMemoryMemoryRepository
from infrastructure.memory.pgvector_repository import PgvectorMemoryRepository
```

(c) Add the backend chooser after `build_service`:

```python
def _memory_repository(db: str) -> MemoryRepository:
    """Choose the memory backend alongside the game persistence backend (spec §3.6)."""
    if db == "memory":
        return InMemoryMemoryRepository()
    if db == "postgres":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set; copy .env.example and configure it "
                "to run with --db postgres"
            )
        return PgvectorMemoryRepository(connect(database_url))
    raise ValueError(f"unknown database backend: {db!r}")
```

(d) `_wire_party` — new signature `(service, game_id, mode, console, db: str)`; the fake `_decision` dict gains `"memory_note": "The orc hits hard; stay at range.",`; and the wiring between the gateway selection and `runtime = AgentRuntime(...)` becomes:

```python
    embedding_profile = model_catalog.get("embedding")
    embedder: EmbeddingGateway
    if mode == "llm":
        embedder = create_embedding_gateway(embedding_profile.provider, api_key=api_key)
    else:
        embedder = DeterministicEmbeddingGateway()
    memory = MemoryService(embedder, _memory_repository(db), model=embedding_profile.model)
    runtime = AgentRuntime(gateway, RetryPolicy())
    agent_service = AgentTurnService(
        service, runtime, model_catalog, agent_profiles, memory=memory
    )
```

(e) In `main`, pass the db flag through:

```python
            agent_service = _wire_party(service, game_id, args.agent, console, args.db)
```

(f) In `_render_agent_turn`, extend the telemetry line with the memory count (counts may be displayed; contents may not):

```python
    console.print(
        f"[dim]agent {report.actor_id} — source: {report.proposal_source}, "
        f"attempts: {report.action_attempts}, llm calls: {len(report.invocations)}, "
        f"memories: {report.memory_retrieved}[/dim]"
    )
```

(g) `README.md` — append at the end of the file:

````markdown

## Agent memory (offline by default)

AI party members remember what happens to them. Each accepted turn records an
**episodic** memory (derived from the turn's domain events) and, when the model
includes a `memory_note` in its decision, a **semantic** one (the model's own
note-to-self). Before each turn the five most relevant memories are retrieved by
embedding similarity and rendered into the agent's prompt.

- `--agent fake` uses a deterministic stdlib embedder and the in-memory
  repository — fully offline.
- `--agent llm` embeds with `openai/text-embedding-3-small` through OpenRouter
  (the one sanctioned carve-out from the cheap-chat-model directive).
- `--db postgres` persists memories to `agent_memories` (pgvector cosine search,
  migration `002_agent_memories.sql`; a PostgreSQL with the `vector` extension
  available is required — pgserver ships it); `--db memory` keeps them in RAM.

Memory is bookkeeping, never a gate: retrieval or embedding failures degrade to
an empty memory for that turn and the game continues (CLAUDE.md §28, §66).
Memory contents are private context and are never logged or displayed outside
the owning agent's own prompt (§20, §34).
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ai/models tests/interfaces -q`
Expected: PASS — the updated shipped-config tests and every existing CLI test (the `--agent fake` CLI tests now exercise the full memory wiring offline: deterministic embedder + in-memory store).

- [ ] **Step 5: Run the full gate**

Run the gate.
Expected: clean; offline count 362. Also verify the domain constraint: `git log master..HEAD --oneline -- src/domain` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add src/interfaces/cli/app.py config/llm.toml tests/ai/models/test_profiles.py README.md
git commit -m "feat(interfaces): wire agent memory into the CLI with the embedding carve-out

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Final verification (spec §8 completion checklist)

After Task 9, run once and confirm every line:

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
.venv/bin/python -m pytest -q                      # 362 passed, 1 skipped (no key set)
OPENROUTER_API_KEY=<real key> .venv/bin/python -m pytest tests/integration/test_openrouter_live.py -q   # 2 passed (optional)
git log master..HEAD --oneline -- src/domain       # prints nothing
git log master..HEAD --oneline                     # 9 commits, one per task
```

- [ ] `src/domain/` has zero diff vs `master`; `src/ai/memory/` purity test passes.
- [ ] `EmbeddingGateway` and `MemoryRepository` are the only memory seams; no consumer imports psycopg, httpx, or provider names outside infrastructure.
- [ ] Memories enter prompts only through `build_user_prompt(memories=...)`; writes happen only after accepted turns; memory failures never fail a turn.
- [ ] `--agent fake` remains fully offline (deterministic embedder, no network).
- [ ] pgvector repository proven against pgserver offline, including the migration.
- [ ] Duplicate memories suppressed; every stored row is embedded (NOT NULL policy).
- [ ] `memory_retrieved` observable; no memory text in logs, CLI output, or telemetry.
- [ ] Full suite green offline without `OPENROUTER_API_KEY` or `DATABASE_URL`.
- [ ] No new runtime dependencies; no provider SDK outside infrastructure.

Then follow the finishing-a-development-branch skill: full suite, environment detection, and the merge/PR/keep menu (base branch: `master`).
