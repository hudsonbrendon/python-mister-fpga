"""Tests for the RetroAchievements Web API module."""
from mister_fpga.const import (
    RA_WEB_API_BASE,
    RA_WEB_DEFAULT_ACHIEVEMENT_MINUTES,
    RA_WEB_DEFAULT_RECENT_COUNT,
    RA_WEB_IMAGE_BASE,
    MisterRAWebStats,
    RAAchievement,
    RAGameProgress,
)


def test_constants():
    assert RA_WEB_API_BASE == "https://retroachievements.org/API/"
    assert RA_WEB_IMAGE_BASE == "https://media.retroachievements.org"
    assert RA_WEB_DEFAULT_RECENT_COUNT == 10
    assert RA_WEB_DEFAULT_ACHIEVEMENT_MINUTES == 10080


def test_game_progress_defaults():
    g = RAGameProgress(game_id=1, title="Game", console="NES")
    assert g.num_achieved == 0
    assert g.num_possible == 0
    assert g.percent == 0.0
    assert g.last_played is None
    assert g.icon_url is None


def test_achievement_defaults():
    a = RAAchievement(title="Win", description="desc", points=10, game_title="G")
    assert a.date is None
    assert a.badge_url is None


def test_web_stats_defaults():
    s = MisterRAWebStats()
    assert s.hardcore_points == 0
    assert s.softcore_points == 0
    assert s.rank is None
    assert s.total_ranked is None
    assert s.current_game is None
    assert s.recent_games == []
    assert s.last_achievement is None
