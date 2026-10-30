"""Tests for the RA debug-log parser and gamepad argument checks."""

from __future__ import annotations

import pytest

from mister_fpga import MisterGamepad, parse_ra_log

LOG = """=== RetroAchievements Debug Log ===
\x1b[32mRA: LOGIN OK: hudson (hardcore: 1200, softcore: 30)\x1b[0m
RA: === GAME IDENTIFIED ===
RA:   ID: 228
RA:   Title: Super Mario World
RA:   ROM: /media/fat/games/SNES/smw.sfc
RA: *** ACHIEVEMENT TRIGGERED: [4874] I'm a Big Boy Now — Collect a mushroom ***
RA: LEADERBOARD SUBMITTED: [12] Speedrun
RA: *** GAME COMPLETED! ***
RA: --- Game Unload ---
"""


def test_parse_ra_log_events():
    events = parse_ra_log(LOG)
    assert [e["type"] for e in events] == [
        "login",
        "game_identified",
        "achievement",
        "leaderboard",
        "game_completed",
        "game_unload",
    ]
    assert events[0] == {
        "type": "login",
        "user": "hudson",
        "hardcore_points": 1200,
        "softcore_points": 30,
    }
    assert events[1] == {
        "type": "game_identified",
        "game_id": 228,
        "title": "Super Mario World",
    }
    assert events[2]["id"] == 4874
    assert events[2]["title"] == "I'm a Big Boy Now"
    assert events[2]["description"] == "Collect a mushroom"


async def test_gamepad_rejects_unknown_input():
    pad = MisterGamepad("h")
    with pytest.raises(ValueError):
        await pad.async_press("turbo")
    with pytest.raises(ValueError):
        await pad.async_press("a", "hold")
