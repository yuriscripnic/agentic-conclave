"""Model profiles: named model configurations loaded from TOML (stdlib tomllib)."""

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai.models.errors import InvalidProfileError, ProfileConfigError, ProfileNotFoundError
from ai.models.types import Message, ModelRequest


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None

    def to_request(self, messages: Sequence[Message]) -> ModelRequest:
        return ModelRequest(
            messages=tuple(messages),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float
    output_per_million_usd: float


@dataclass
class ModelProfileCatalog:
    default_provider: str
    profiles: Mapping[str, ModelProfile]
    pricing: Mapping[str, ModelPricing]

    def get(self, name: str) -> ModelProfile:
        try:
            return self.profiles[name]
        except KeyError:
            raise ProfileNotFoundError(f"unknown model profile: {name!r}") from None


def load_model_profiles(path: str | Path) -> ModelProfileCatalog:
    """Load profiles and pricing from a TOML file (structure validation only)."""
    file = Path(path)
    if not file.is_file():
        raise ProfileConfigError(f"model profile config not found: {file}")
    try:
        raw = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProfileConfigError(f"invalid TOML in {file}: {exc}") from exc

    profiles: dict[str, ModelProfile] = {}
    for name, entry in raw.get("profiles", {}).items():
        if not isinstance(entry, Mapping) or "provider" not in entry or "model" not in entry:
            raise InvalidProfileError(f"profile {name!r} must define provider and model")
        max_tokens = entry.get("max_tokens")
        profiles[name] = ModelProfile(
            name=name,
            provider=str(entry["provider"]),
            model=str(entry["model"]),
            temperature=float(entry.get("temperature", 0.7)),
            max_tokens=int(max_tokens) if max_tokens is not None else None,
        )

    pricing: dict[str, ModelPricing] = {}
    for model_id, entry in raw.get("pricing", {}).items():
        required = ("input_per_million_usd", "output_per_million_usd")
        if not isinstance(entry, Mapping) or any(key not in entry for key in required):
            raise InvalidProfileError(
                f"pricing for {model_id!r} must define input and output per-million USD"
            )
        pricing[model_id] = ModelPricing(
            input_per_million_usd=float(entry["input_per_million_usd"]),
            output_per_million_usd=float(entry["output_per_million_usd"]),
        )

    return ModelProfileCatalog(
        default_provider=str(raw.get("default_provider", "openrouter")),
        profiles=profiles,
        pricing=pricing,
    )
