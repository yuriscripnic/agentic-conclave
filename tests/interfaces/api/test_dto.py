"""DTO mapper tests: HTTP responses mirror application views field-for-field."""

from dto_fixtures import build_game_view, build_turn_report

from domain.common.ids import EventId
from domain.events.collector import EventEnvelope
from interfaces.api.dto import (
    event_response,
    game_view_response,
    status_response,
    turn_report_response,
)


def test_game_view_response_mirrors_view() -> None:
    view = build_game_view()

    response = game_view_response(view)

    assert response.game_id == "game-1"
    assert response.status == "running"
    assert response.party[0].name == "Arin"
    assert response.party[0].hp_current == 12
    assert response.combat is not None
    assert response.combat.round_number == 1


def test_turn_report_response_serializes_report() -> None:
    report = build_turn_report()

    response = turn_report_response(report)

    assert response.accepted is True
    assert response.game_over is False
    assert response.events == []
    assert response.view.game_id == "game-1"


def test_event_response_shape() -> None:
    envelope = EventEnvelope(
        sequence=1,
        event_id=EventId("e1"),
        game_id=EventId("game-1"),
        occurred_at="2026-09-13T12:00:00+00:00",
        event_type="GameCreated",
        payload={"campaign": "x"},
    )

    response = event_response(envelope)

    assert response.sequence == 1
    assert response.event_type == "GameCreated"
    assert response.payload == {"campaign": "x"}


def test_status_response_active_combat_not_over() -> None:
    status = status_response(build_game_view())

    assert status.status == "running"
    assert status.game_over is False
    assert status.combat is not None


def test_status_response_ended_combat_marks_game_over() -> None:
    from dataclasses import replace

    from dto_fixtures import build_game_view

    view = replace(build_game_view(), combat=replace(build_game_view().combat, status="ended"))
    status = status_response(view)

    assert status.game_over is True


def test_status_response_without_combat() -> None:
    from dataclasses import replace

    from dto_fixtures import build_game_view

    status = status_response(replace(build_game_view(), combat=None))

    assert status.game_over is False
    assert status.combat is None
