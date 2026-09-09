"""GmProfile loader tests — shipped config + explicit validation errors."""

from pathlib import Path

import pytest

from application.gm.profiles import GmProfileError, load_gm_profile


def test_load_gm_profile_reads_the_shipped_config() -> None:
    profile = load_gm_profile(Path(__file__).parents[3] / "config" / "gm.toml")
    assert profile.name == "The Dungeon Master"
    assert "second-person" in profile.style
    assert profile.narration_max_chars == 280
    assert profile.reply_max_chars == 200
    assert profile.history_limit == 12


def test_missing_required_fields_raise(tmp_path: Path) -> None:
    config = tmp_path / "gm.toml"
    config.write_text('[gm]\nname = "DM"\n', encoding="utf-8")
    with pytest.raises(GmProfileError, match="missing fields"):
        load_gm_profile(config)


def test_invalid_cap_values_raise(tmp_path: Path) -> None:
    config = tmp_path / "gm.toml"
    config.write_text(
        '[gm]\nname = "DM"\nstyle = "s"\nnarration_max_chars = 0\n',
        encoding="utf-8",
    )
    with pytest.raises(GmProfileError, match="narration_max_chars"):
        load_gm_profile(config)
