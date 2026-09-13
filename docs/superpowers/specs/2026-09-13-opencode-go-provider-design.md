# OpenCode Go Provider Migration — Design

**Date:** 2026-09-13
**Status:** Approved (user decision 2026-09-13; embedding fallback = option 1)
**Supersedes:** OpenRouter as default provider (Plan 3, `docs/superpowers/specs/2026-09-04-model-gateway-design.md`)

## Context

The project's default LLM provider is OpenRouter serving `z-ai/glm-5.3-flash`.
The user directed (2026-09-13) that the project use **OpenCode Go** instead.
OpenCode Go is an OpenAI-compatible subscription gateway:

- Base URL: `https://opencode.ai/zen/go/v1` (chat: `/chat/completions`)
- Model ID: `glm-5.3-flash` (the same model the project already uses)
- Pricing (verified 2026-09-13, https://opencode.ai/docs/go/): $0.15 input / $0.50 output per million tokens
- API key: user-level, from the OpenCode Zen console → env var `OPENCODE_API_KEY`
- **No `/embeddings` endpoint** — chat completions only
- Client etiquette (docs): send a self-identifying `User-Agent` (not a generic
  SDK name) and a stable `x-opencode-session` header per conversation

## Decisions

1. **Add `opencode-go` as a registered provider; make it the default.**
   The OpenRouter adapter stays registered and functional (existing live
   integration tests and the optional embeddings path still use it). No code
   that names OpenRouter is deleted.

2. **Reuse, don't duplicate.** `OpenCodeGoModelGateway` subclasses
   `OpenRouterModelGateway` (both are OpenAI-compatible). The base class is
   generalized minimally: provider name, default base URL, and extra headers
   become class-level hooks. No new dependency; `httpx` is already in use.

3. **Config switch.** `config/llm.toml`:
   - `default_provider = "opencode-go"`
   - All chat profiles (`gm`, `player`, `cheap`, `reasoning`, `creative`):
     `provider = "opencode-go"`, `model = "glm-5.3-flash"`
   - `[profiles.embedding]` unchanged (`openrouter` / `openai/text-embedding-3-small`)
   - Pricing: add `glm-5.3-flash` (0.15/0.50) and `glm-5.2` (1.40/4.40, the
     Go upgrade path); remove the now-unused `z-ai/*` entries; keep
     `openai/text-embedding-3-small` (0.02/0.0)

4. **Embeddings fall back to the deterministic embedder** (user decision,
   option 1). When the resolved chat provider is `opencode-go`, the session
   factory wires `DeterministicEmbeddingGateway` for agent memory, because Go
   has no embeddings endpoint. pgvector storage is unchanged. When the chat
   provider is `openrouter`, the real embeddings gateway is used as today.

5. **API key resolution.** The session factory maps provider → env var:
   `opencode-go` → `OPENCODE_API_KEY`, `openrouter` →
   `OPENROUTER_API_KEY`. Error messages name the variable the user must set.
   Unknown providers keep raising `UnknownProviderError` from the factory.

6. **Evaluation CLI.** `conclave-eval --provider` gains the `opencode-go`
   choice (same `llm/llm` modes as `openrouter`); its API-key preflight check
   uses the same provider → env var mapping.

7. **Go client etiquette.** The adapter sends `User-Agent:
   agentic-conclave/0.1` and `x-opencode-session: <uuid4 hex>` (stable per
   gateway instance) on every request. OpenRouter's `HTTP-Referer`/`X-Title`
   headers stay OpenRouter-only.

8. **`embed()` on the Go gateway raises `ModelError`** ("does not expose an
   embeddings endpoint"). `create_embedding_gateway("opencode-go", ...)` keeps
   raising `UnknownProviderError` (Go is not registered as an embedding
   provider).

## Non-goals

- No sanitization for the known upstream Go/GLM-5.3-Flash tokenizer bug
  (U+00D7 and some trailing quotes → HTTP 400 `[1210]`,
  anomalyco/opencode#46378). Revisit only if it bites in practice.
- No changes to domain, rules engine, application services, or memory
  retrieval semantics. The only application-layer touch is the composition
  root (`src/session/factory.py`) and the eval CLI/runner choices.

## Architecture

```text
infrastructure/llm/
├── __init__.py                  # _PROVIDERS: {"openrouter": …, "opencodego": OpenCodeGoModelGateway}
├── openrouter/adapter.py        # generalized base (provider name, base URL, headers)
└── opencodego/adapter.py        # OpenCodeGoModelGateway(OpenRouterModelGateway)
```

`create_gateway("opencode-go", api_key=…)` returns the new adapter. Registry
keys equal the user-facing provider strings (`"openrouter"`, `"opencode-go"`)
so config values pass through unchanged.

## Testing

- Unit: `httpx.MockTransport` tests for the Go adapter (URL, auth, headers,
  usage/cost mapping, provider label in `LLMInvocation`, embed rejection,
  empty-key rejection) — no network.
- Unit: shipped-config profile tests updated to the new provider/model/pricing.
- Unit: session factory env-var mapping and deterministic-embedder fallback.
- Unit: eval CLI provider choice and preflight exit code 2 without the key.
- Integration (skipped without `OPENCODE_API_KEY`, CLAUDE.md §46): live
  generate smoke test, mirroring `tests/integration/test_openrouter_live.py`.
- Full suite green; OpenRouter suites untouched and passing.

## Security

- Secrets only via env vars; nothing committed. `.env.example` lists
  `OPENCODE_API_KEY` first; `OPENROUTER_API_KEY` stays documented for the
  optional embeddings path.
- Adapter logs no keys, prompts, or payloads (unchanged behavior).
