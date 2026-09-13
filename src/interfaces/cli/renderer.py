"""Rich rendering of application views — presentation only (CLAUDE.md §42)."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from application.gm.director import GmResult
from application.views import CharacterView, GameView, TurnReport
from domain.events.collector import EventEnvelope


def render_game_view(console: Console, view: GameView) -> None:
    console.print(
        Panel(
            f"[bold]{view.campaign_name}[/bold] — game {view.game_id}"
            f" — status: {view.status}",
            expand=False,
        )
    )
    console.print(_roster_table("Party", view.party))
    console.print(_roster_table("Enemies", view.enemies))
    if view.scene is not None:
        scene = view.scene
        exits_text = ", ".join(
            f"{direction} -> {destination}" for direction, destination in scene.exits
        )
        console.print(
            f"Scene: [bold]{scene.name}[/bold] — {scene.description}"
            f"\nExits: {exits_text or 'none'}"
        )
        if view.combat is None:
            console.print("Actions: go <exit>, say <text> — /status /help /quit")
            return
    if view.combat is None:
        return
    combat = view.combat
    header = f"Round {combat.round_number} — combat {combat.status}"
    if combat.active_actor_id is not None:
        header += f" — {_name_for(view, combat.active_actor_id)}'s turn"
    console.print(header)
    console.print(
        "Initiative: "
        + ", ".join(f"{e.name} ({e.total})" for e in combat.initiative_order)
    )
    console.print("Actions: attack <target> — /status /help /quit")


def _roster_table(title: str, members: Sequence[CharacterView]) -> Table:
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Class")
    table.add_column("Level")
    table.add_column("HP")
    table.add_column("AC")
    table.add_column("Conditions")
    for member in members:
        table.add_row(
            member.name,
            member.character_class or "-",
            str(member.level),
            f"{member.hp_current}/{member.hp_max}",
            str(member.armor_class),
            ", ".join(member.conditions) or "-",
        )
    return table


def _name_for(view: GameView, character_id: str) -> str:
    for member in (*view.party, *view.enemies):
        if member.id == character_id:
            return member.name
    return character_id


def render_report(console: Console, report: TurnReport, view: GameView) -> None:
    name_by_id = {m.id: m.name for m in (*view.party, *view.enemies)}
    for envelope in report.events:
        line = describe_event(envelope, name_by_id)
        if line is not None:
            console.print(line)


def describe_event(
    envelope: EventEnvelope, name_by_id: dict[str, str]
) -> str | None:
    payload = envelope.payload
    if envelope.event_type == "attack_resolved":
        attacker = name_by_id.get(
            str(payload["attacker_id"]), str(payload["attacker_id"])
        )
        target = name_by_id.get(str(payload["target_id"]), str(payload["target_id"]))
        if payload["critical"]:
            outcome = "CRITICAL HIT"
        elif payload["hit"]:
            outcome = "HIT"
        else:
            outcome = "MISS"
        return (
            f"⚔ {attacker} attacks {target}: d20 {payload['roll']} +"
            f"{payload['attack_bonus']} = {payload['total']} vs AC {payload['target_ac']}"
            f" — {outcome}"
        )
    if envelope.event_type == "damage_applied":
        name = name_by_id.get(
            str(payload["character_id"]), str(payload["character_id"])
        )
        return (
            f"💥 {name} takes {payload['amount']} damage"
            f" ({payload['hp_before']} → {payload['hp_after']})"
        )
    if envelope.event_type == "character_defeated":
        name = name_by_id.get(
            str(payload["character_id"]), str(payload["character_id"])
        )
        return f"☠ {name} is defeated!"
    if envelope.event_type == "action_rejected":
        return f"✗ Action rejected: {payload['reason']}"
    if envelope.event_type == "combat_ended":
        return (
            f"🏆 {payload['winner_side']} wins the combat"
            f" in round {payload['round_number']}!"
        )
    # initiative_rolled / game_* / turn_* / attack_requested events stay silent
    return None


def render_gm_result(console: Console, result: GmResult, view: GameView) -> None:
    """Render GM narration/NPC replies; prints nothing for an empty GmResult (D10).

    `view` is reserved for future scene-aware styling (spec §3.6).
    """
    if result.npc_reply is not None:
        speaker = result.addressed_to or "gm"
        console.print(f"[magenta]{speaker}:[/magenta] {result.npc_reply}")
    if result.narration is not None:
        console.print(f"[dim italic]{result.narration}[/dim italic]")
