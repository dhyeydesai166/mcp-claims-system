from minimal_server import ping


def test_ping_returns_pong() -> None:
    assert ping("equipment") == "pong equipment"
