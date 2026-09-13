from pathlib import Path

import pytest

from ai.models.errors import InvalidProfileError, ProfileConfigError, ProfileNotFoundError
from ai.models.profiles import ModelPricing, load_model_profiles
from ai.models.types import Message

_MINIMAL_TOML = """\
default_provider = "openrouter"

[profiles.gm]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"
temperature = 0.8
max_tokens = 1024

[profiles.cheap]
provider = "openrouter"
model = "z-ai/glm-5.3-flash"

[pricing."z-ai/glm-5.3-flash"]
input_per_million_usd = 0.07125
output_per_million_usd = 0.2375
"""


def _write(tmp_path: Path, content: str) -> Path:
    config = tmp_path / "llm.toml"
    config.write_text(content, encoding="utf-8")
    return config


def test_loads_profiles_and_pricing(tmp_path: Path) -> None:
    catalog = load_model_profiles(_write(tmp_path, _MINIMAL_TOML))

    assert catalog.default_provider == "openrouter"
    gm = catalog.get("gm")
    assert gm.model == "z-ai/glm-5.3-flash"
    assert gm.temperature == 0.8
    assert gm.max_tokens == 1024

    cheap = catalog.get("cheap")
    assert cheap.temperature == 0.7
    assert cheap.max_tokens is None

    assert catalog.pricing["z-ai/glm-5.3-flash"] == ModelPricing(
        input_per_million_usd=0.07125, output_per_million_usd=0.2375
    )


def test_unknown_profile_raises(tmp_path: Path) -> None:
    catalog = load_model_profiles(_write(tmp_path, _MINIMAL_TOML))
    with pytest.raises(ProfileNotFoundError, match="nope"):
        catalog.get("nope")


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProfileConfigError):
        load_model_profiles(tmp_path / "absent.toml")


def test_profile_missing_model_raises(tmp_path: Path) -> None:
    config = _write(
        tmp_path, 'default_provider = "openrouter"\n[profiles.gm]\nprovider = "openrouter"\n'
    )
    with pytest.raises(InvalidProfileError, match="gm"):
        load_model_profiles(config)


def test_to_request_builds_model_request(tmp_path: Path) -> None:
    catalog = load_model_profiles(_write(tmp_path, _MINIMAL_TOML))
    request = catalog.get("gm").to_request([Message(role="user", content="hi")])
    assert request.model == "z-ai/glm-5.3-flash"
    assert request.messages == (Message(role="user", content="hi"),)
    assert request.temperature == 0.8
    assert request.max_tokens == 1024


def test_shipped_config_has_six_cheap_profiles() -> None:
    config = Path(__file__).parents[3] / "config" / "llm.toml"
    catalog = load_model_profiles(config)
    assert catalog.default_provider == "opencode-go"
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
        assert profile.provider == "opencode-go"
        assert profile.model == "glm-5.3-flash"
    assert set(catalog.pricing) == {
        "glm-5.3-flash",
        "glm-5.2",
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


def test_missing_default_provider_raises(tmp_path: Path) -> None:
    config = _write(tmp_path, '[profiles.gm]\nprovider = "openrouter"\nmodel = "m"\n')
    with pytest.raises(ProfileConfigError, match="default_provider"):
        load_model_profiles(config)
