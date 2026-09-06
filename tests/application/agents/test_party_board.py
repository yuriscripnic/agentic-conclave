"""PartyMessageBoard tests — the §32 broadcast board (agent-layer, not game truth)."""

from application.agents.party_board import PartyMessage, PartyMessageBoard


def _message(
    name: str = "Brix", text: str = "Focus the orc.", round_number: int = 1
) -> PartyMessage:
    return PartyMessage(actor_name=name, text=text, round_number=round_number)


def test_empty_board_returns_no_messages() -> None:
    assert PartyMessageBoard().recent() == ()


def test_recent_returns_messages_in_chronological_order() -> None:
    board = PartyMessageBoard()
    board.post(_message(text="first"))
    board.post(_message(name="Mira", text="second", round_number=2))
    recent = board.recent()
    assert [message.text for message in recent] == ["first", "second"]
    assert recent[1].actor_name == "Mira"
    assert recent[1].round_number == 2


def test_recent_bounds_the_read() -> None:
    board = PartyMessageBoard()
    for index in range(10):
        board.post(_message(text=f"msg-{index}"))
    recent = board.recent(limit=8)
    assert [message.text for message in recent] == [f"msg-{index}" for index in range(2, 10)]


def test_non_positive_limit_returns_no_messages() -> None:
    board = PartyMessageBoard()
    board.post(_message())
    assert board.recent(limit=0) == ()
    assert board.recent(limit=-3) == ()


def test_returned_tuple_is_independent_of_later_posts() -> None:
    board = PartyMessageBoard()
    board.post(_message(text="first"))
    recent = board.recent()
    board.post(_message(text="second"))
    assert len(recent) == 1
