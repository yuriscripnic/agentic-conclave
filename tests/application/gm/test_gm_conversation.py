"""GmConversation tests — bounded reads over an in-RAM board (spec §3.2)."""

from application.gm.conversation import GmConversation, GmMessage


def test_append_then_recent_returns_lines_in_order() -> None:
    board = GmConversation()
    board.append(GmMessage(speaker="player", text="Hello?"))
    board.append(GmMessage(speaker="Orc Brute", text="Fresh meat!"))
    assert board.recent(10) == (
        GmMessage(speaker="player", text="Hello?"),
        GmMessage(speaker="Orc Brute", text="Fresh meat!"),
    )


def test_recent_evicts_to_the_limit() -> None:
    board = GmConversation()
    for index in range(5):
        board.append(GmMessage(speaker="player", text=str(index)))
    assert [message.text for message in board.recent(3)] == ["2", "3", "4"]


def test_non_positive_limit_returns_empty() -> None:
    board = GmConversation()
    board.append(GmMessage(speaker="player", text="Hi"))
    assert board.recent(0) == ()
    assert board.recent(-1) == ()


def test_recent_on_an_empty_board_is_empty() -> None:
    assert GmConversation().recent(5) == ()
