"""GM profile loading (spec §3.1) — explicit config errors, no silent defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class GmProfileError(ValueError):
    """Raised when config/gm.toml is missing required fields or has bad types."""


@dataclass(frozen=True)
class GmProfile:
    name: str
    style: str
    narration_max_chars: int
    reply_max_chars: int
    history_limit: int


_CAP_DEFAULTS: dict[str, int] = {
    "narration_max_chars": 280,
    "reply_max_chars": 200,
    "history_limit": 12,
}


def load_gm_profile(path: str | Path) -> GmProfile:
    """Read a [gm] table from a TOML file and validate it."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GmProfileError(f"GM profile file not found: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise GmProfileError(f"GM profile file is not valid TOML: {error}") from error
    table = data.get("gm")
    if not isinstance(table, dict):
        raise GmProfileError("gm.toml must contain a [gm] table")
    missing = {"name", "style"} - set(table)
    if missing:
        raise GmProfileError(f"[gm] missing fields: {sorted(missing)}")
    for key in ("name", "style"):
        if not isinstance(table[key], str) or not table[key].strip():
            raise GmProfileError(f"[gm] {key} must be a non-empty string")
    values: dict[str, int] = {}
    for key, default in _CAP_DEFAULTS.items():
        raw = table.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
            raise GmProfileError(f"[gm] {key} must be an int >= 1")
        values[key] = raw
    return GmProfile(
        name=table["name"],
        style=table["style"],
        narration_max_chars=values["narration_max_chars"],
        reply_max_chars=values["reply_max_chars"],
        history_limit=values["history_limit"],
    )
