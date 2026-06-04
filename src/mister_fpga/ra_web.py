"""RetroAchievements.org Web API client and parsers (cloud player stats)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import (
    RA_WEB_API_BASE,
    RA_WEB_DEFAULT_ACHIEVEMENT_MINUTES,
    RA_WEB_DEFAULT_RECENT_COUNT,
    RA_WEB_IMAGE_BASE,
    MisterRAWebStats,
    RAAchievement,
    RAGameProgress,
)

_LOGGER = logging.getLogger(__name__)


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


class MisterRAWebError(Exception):
    """A RetroAchievements Web API request failed (network, HTTP, or auth)."""


class MisterRAWeb:
    """Async client for the public RetroAchievements.org Web API.

    Args:
        username: RA account username (used for both ``z`` and ``u``).
        api_key: RA Web API key (``y``), from retroachievements.org/settings.
        session: Optional shared ``aiohttp.ClientSession``. When ``None`` the
            client creates and owns one; call :meth:`async_close` to release it.
        timeout: Per-request timeout in seconds (default ``15``).
    """

    def __init__(
        self,
        username: str,
        api_key: str,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: int = 15,
    ) -> None:
        self.username = username
        self._api_key = api_key
        self._timeout = timeout
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def async_close(self) -> None:
        """Close the HTTP session if this client created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        session = await self._get_session()
        url = f"{RA_WEB_API_BASE}{endpoint}"
        query = {"z": self.username, "y": self._api_key, "u": self.username, **params}
        try:
            async with session.get(
                url,
                params=query,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as err:
                    raise MisterRAWebError(
                        f"{endpoint} returned invalid JSON: {err}"
                    ) from err
                if isinstance(data, dict) and data.get("Error"):
                    raise MisterRAWebError(f"{endpoint} error: {data['Error']}")
                return data
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.debug("RA Web request %s failed: %s", endpoint, err)
            raise MisterRAWebError(f"{endpoint} failed: {err}") from err

    async def async_get_rank_and_score(self) -> dict:
        return await self._request("API_GetUserRankAndScore.php", {})

    async def async_get_recently_played(
        self, count: int = RA_WEB_DEFAULT_RECENT_COUNT
    ) -> list:
        return await self._request(
            "API_GetUserRecentlyPlayedGames.php", {"c": count}
        )

    async def async_get_recent_achievements(
        self, minutes: int = RA_WEB_DEFAULT_ACHIEVEMENT_MINUTES
    ) -> list:
        return await self._request(
            "API_GetUserRecentAchievements.php", {"m": minutes}
        )

    async def async_fetch_stats(self) -> MisterRAWebStats:
        """Fetch all cloud stats concurrently and assemble them."""
        rank_raw, games_raw, ach_raw = await asyncio.gather(
            self.async_get_rank_and_score(),
            self.async_get_recently_played(),
            self.async_get_recent_achievements(),
        )
        hardcore, softcore, rank, total = parse_rank_and_score(rank_raw)
        games = parse_recently_played(games_raw)
        achievements = parse_recent_achievements(ach_raw)
        return MisterRAWebStats(
            hardcore_points=hardcore,
            softcore_points=softcore,
            rank=rank,
            total_ranked=total,
            current_game=games[0] if games else None,
            recent_games=games,
            last_achievement=achievements[0] if achievements else None,
        )

    async def async_validate(self) -> None:
        """Verify credentials with a lightweight call. Raises on failure."""
        await self.async_get_rank_and_score()

    async def async_get_badge_image(self, url: str) -> bytes:
        """Fetch a badge/icon image by absolute URL."""
        session = await self._get_session()
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                return await resp.read()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise MisterRAWebError(f"badge fetch failed: {err}") from err
