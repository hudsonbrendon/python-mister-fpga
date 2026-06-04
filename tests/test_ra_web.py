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
from mister_fpga.ra_web import (
    parse_rank_and_score,
    parse_recent_achievements,
    parse_recently_played,
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


def test_parse_rank_and_score():
    raw = {"Score": 12345, "SoftcoreScore": 678, "Rank": 9876, "TotalRanked": 543210}
    points_h, points_s, rank, total = parse_rank_and_score(raw)
    assert points_h == 12345
    assert points_s == 678
    assert rank == 9876
    assert total == 543210


def test_parse_rank_and_score_missing_keys():
    points_h, points_s, rank, total = parse_rank_and_score({})
    assert points_h == 0
    assert points_s == 0
    assert rank is None
    assert total is None


def test_parse_recently_played_builds_progress_with_percent_and_absolute_icon():
    raw = [
        {
            "GameID": 1,
            "Title": "Super Mario Bros.",
            "ConsoleName": "NES",
            "NumAchieved": 5,
            "NumPossibleAchievements": 10,
            "LastPlayed": "2024-01-01 12:00:00",
            "ImageIcon": "/Images/024529.png",
        }
    ]
    games = parse_recently_played(raw)
    assert len(games) == 1
    g = games[0]
    assert g.game_id == 1
    assert g.title == "Super Mario Bros."
    assert g.console == "NES"
    assert g.num_achieved == 5
    assert g.num_possible == 10
    assert g.percent == 50.0
    assert g.last_played == "2024-01-01 12:00:00"
    assert g.icon_url == "https://media.retroachievements.org/Images/024529.png"


def test_parse_recently_played_zero_possible_is_zero_percent():
    games = parse_recently_played(
        [
            {
                "GameID": 2,
                "Title": "X",
                "ConsoleName": "SNES",
                "NumPossibleAchievements": 0,
            }
        ]
    )
    assert games[0].percent == 0.0


def test_parse_recently_played_empty():
    assert parse_recently_played([]) == []


def test_parse_recent_achievements_prefers_badge_url_then_builds_from_name():
    raw = [
        {
            "Title": "Win",
            "Description": "Beat it",
            "Points": 10,
            "GameTitle": "Super Mario Bros.",
            "Date": "2024-01-02 09:00:00",
            "BadgeURL": "/Badge/12345.png",
        },
        {
            "Title": "Older",
            "Description": "d",
            "Points": 5,
            "GameTitle": "G",
            "Date": "2024-01-01 09:00:00",
            "BadgeName": "67890",
        },
    ]
    achs = parse_recent_achievements(raw)
    assert achs[0].title == "Win"
    assert achs[0].points == 10
    assert achs[0].badge_url == "https://media.retroachievements.org/Badge/12345.png"
    assert achs[1].badge_url == "https://media.retroachievements.org/Badge/67890.png"


def test_parse_recent_achievements_empty():
    assert parse_recent_achievements([]) == []
