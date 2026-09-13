"""Lightweight GameView/TurnReport builders for DTO tests."""
from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
    TurnReport,
)


def build_game_view() -> GameView:
    return GameView(
        game_id="game-1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[
            CharacterView(
                id="arin",
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
        enemies=[],
        combat=CombatView(
            round_number=1,
            status="active",
            active_actor_id="arin",
            initiative_order=[InitiativeEntryView(character_id="arin", name="Arin", total=15)],
        ),
    )


def build_turn_report() -> TurnReport:
    return TurnReport(
        game_id="game-1",
        accepted=True,
        error_code="",
        reason="",
        events=[],
        view=build_game_view(),
        game_over=False,
    )
