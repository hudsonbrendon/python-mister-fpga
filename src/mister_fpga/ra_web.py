"""RetroAchievements.org Web API client and parsers (cloud player stats)."""
from __future__ import annotations

from .const import (
    RA_WEB_IMAGE_BASE,
    RAAchievement,
    RAGameProgress,
)


def _abs_image(path: str | None) -> str | None:
    """Resolve a relative RA image path to an absolute media URL."""
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{RA_WEB_IMAGE_BASE}{path}"


def parse_rank_and_score(raw: dict) -> tuple[int, int, int | None, int | None]:
    """Return (hardcore_points, softcore_points, rank, total_ranked)."""
    if not isinstance(raw, dict):
        return 0, 0, None, None
    hardcore = int(raw.get("Score") or 0)
    softcore = int(raw.get("SoftcoreScore") or 0)
    rank = raw.get("Rank")
    total = raw.get("TotalRanked")
    return (
        hardcore,
        softcore,
        int(rank) if rank is not None else None,
        int(total) if total is not None else None,
    )


def parse_recently_played(raw: list) -> list[RAGameProgress]:
    """Build RAGameProgress entries (most-recent first, as the API returns)."""
    games: list[RAGameProgress] = []
    if not isinstance(raw, list):
        return games
    for item in raw:
        if not isinstance(item, dict):
            continue
        achieved = int(item.get("NumAchieved") or 0)
        possible = int(item.get("NumPossibleAchievements") or 0)
        percent = round(achieved / possible * 100, 1) if possible else 0.0
        games.append(
            RAGameProgress(
                game_id=int(item.get("GameID") or 0),
                title=item.get("Title") or "",
                console=item.get("ConsoleName") or "",
                num_achieved=achieved,
                num_possible=possible,
                percent=percent,
                last_played=item.get("LastPlayed"),
                icon_url=_abs_image(item.get("ImageIcon")),
            )
        )
    return games


def parse_recent_achievements(raw: list) -> list[RAAchievement]:
    """Build RAAchievement entries (most-recent first, as the API returns)."""
    achievements: list[RAAchievement] = []
    if not isinstance(raw, list):
        return achievements
    for item in raw:
        if not isinstance(item, dict):
            continue
        badge = item.get("BadgeURL")
        if not badge and item.get("BadgeName"):
            badge = f"/Badge/{item['BadgeName']}.png"
        achievements.append(
            RAAchievement(
                title=item.get("Title") or "",
                description=item.get("Description") or "",
                points=int(item.get("Points") or 0),
                game_title=item.get("GameTitle") or "",
                date=item.get("Date"),
                badge_url=_abs_image(badge),
            )
        )
    return achievements
