"""The information-asymmetry boundary (CLAUDE.md §20): perception by field selection."""

from __future__ import annotations

from dataclasses import dataclass

from application.views import CharacterView, GameView


class AgentNotInCombatError(RuntimeError):
    """Raised when the actor is not the active combatant in a running combat."""


@dataclass(frozen=True)
class OpponentBrief:
    """What an agent may know about an opponent: identity and standing, never HP/AC."""

    id: str
    name: str
    is_defeated: bool


@dataclass(frozen=True)
class AgentPerception:
    round_number: int
    active_actor_id: str
    self_view: CharacterView
    opponents: tuple[OpponentBrief, ...]
    initiative_order: tuple[str, ...]
    location: str | None = None


def _find(characters: list[CharacterView], actor_id: str) -> CharacterView | None:
    for character in characters:
        if character.id == actor_id:
            return character
    return None


def _opponents_of(view: GameView, self_view: CharacterView) -> list[CharacterView]:
    is_party = any(character.id == self_view.id for character in view.party)
    return view.enemies if is_party else view.party


def build_perception(view: GameView, actor_id: str) -> AgentPerception:
    """Project the actor's slice of the GameView; opponents are name + defeated status only."""
    if view.combat is None or view.combat.active_actor_id is None:
        raise AgentNotInCombatError(f"character {actor_id} has no active combat turn")
    if view.combat.active_actor_id != actor_id:
        raise AgentNotInCombatError(
            f"character {actor_id} is not the active combatant "
            f"(active: {view.combat.active_actor_id})"
        )
    self_view = _find(view.party, actor_id) or _find(view.enemies, actor_id)
    if self_view is None:
        raise AgentNotInCombatError(f"character {actor_id} is not part of this game")

    opponents = tuple(
        OpponentBrief(id=character.id, name=character.name, is_defeated=character.is_defeated)
        for character in _opponents_of(view, self_view)
    )
    initiative_order = tuple(entry.name for entry in view.combat.initiative_order)
    return AgentPerception(
        round_number=view.combat.round_number,
        active_actor_id=view.combat.active_actor_id,
        self_view=self_view,
        opponents=opponents,
        initiative_order=initiative_order,
    )


def first_living_opponent(view: GameView, actor_id: str) -> str | None:
    """The deterministic fallback target: the first living opponent of the actor's side."""
    self_view = _find(view.party, actor_id) or _find(view.enemies, actor_id)
    if self_view is None:
        raise AgentNotInCombatError(f"character {actor_id} is not part of this game")
    for character in _opponents_of(view, self_view):
        if not character.is_defeated:
            return character.id
    return None
