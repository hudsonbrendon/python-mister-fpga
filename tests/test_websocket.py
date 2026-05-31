"""Tests for the MiSTer FPGA WebSocket message parsing."""
from __future__ import annotations

from mister_fpga.client import MisterStatus
from mister_fpga.websocket import MisterWebSocketClient, apply_ws_message


def test_core_running_updates_status():
    status = MisterStatus(online=True, core="MENU")
    new, menu, idx = apply_ws_message("coreRunning:SNES", status, None, (False, False))
    assert new.core == "SNES"


def test_core_running_blank_means_menu():
    status = MisterStatus(online=True, core="SNES", game="x", game_name="X")
    new, menu, idx = apply_ws_message("coreRunning:", status, None, (False, False))
    assert new.core is None
    assert new.game is None


def test_game_running_updates_status():
    status = MisterStatus(online=True, core="SNES")
    new, menu, idx = apply_ws_message(
        "gameRunning:SNES/Chrono.sfc", status, None, (False, False)
    )
    assert new.game == "SNES/Chrono.sfc"
    assert new.game_name == "Chrono"


def test_menu_navigation_sets_path():
    status = MisterStatus(online=True)
    new, menu, idx = apply_ws_message(
        "menuNavigation:_Console/SNES", status, None, (False, False)
    )
    assert menu == "_Console/SNES"


def test_index_status_parsed():
    status = MisterStatus(online=True)
    new, menu, (exists, in_progress) = apply_ws_message(
        "indexStatus:y,n,0,0,", status, None, (False, False)
    )
    assert exists is True
    assert in_progress is False


def test_unknown_message_is_noop():
    status = MisterStatus(online=True, core="SNES")
    new, menu, idx = apply_ws_message(
        "somethingElse:42", status, "_Console", (True, False)
    )
    assert new.core == "SNES"
    assert menu == "_Console"
    assert idx == (True, False)


def test_game_running_preserves_dots_and_spaces():
    status = MisterStatus(online=True, core="PSX")
    new, menu, idx = apply_ws_message(
        "gameRunning:PSX/Crash Bandicoot (USA).chd", status, None, (False, False)
    )
    assert new.game == "PSX/Crash Bandicoot (USA).chd"
    assert new.game_name == "Crash Bandicoot (USA)"


def test_websocket_client_url():
    ws = MisterWebSocketClient("192.168.1.50")
    assert ws.url == "ws://192.168.1.50:8182/api/ws"


def test_websocket_client_url_custom_port():
    ws = MisterWebSocketClient("h", port=9000)
    assert ws.url == "ws://h:9000/api/ws"


def test_websocket_client_stop_sets_flag():
    ws = MisterWebSocketClient("h")
    assert ws._stop is False
    ws.stop()
    assert ws._stop is True
