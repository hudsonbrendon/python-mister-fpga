"""Async REST client for the MiSTer FPGA mrext Remote API."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
import logging
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    BACKGROUND_MODES,
    PATH_CORE_MENU,
    PATH_GAMES_INDEX,
    PATH_GAMES_LAUNCH,
    PATH_GAMES_SEARCH,
    PATH_GAMES_VIEW,
    PATH_INIS,
    PATH_KEYBOARD,
    PATH_KEYBOARD_RAW,
    PATH_LAUNCH,
    PATH_LAUNCH_MENU,
    PATH_LAUNCH_NEW,
    PATH_LAUNCH_TOKEN,
    PATH_MENU_VIEW,
    PATH_MUSIC_NEXT,
    PATH_MUSIC_PLAY,
    PATH_MUSIC_PLAYBACK,
    PATH_MUSIC_PLAYLIST,
    PATH_MUSIC_STATUS,
    PATH_MUSIC_STOP,
    PATH_PEERS,
    PATH_PLAYING,
    PATH_PLAYLOG_GAMES,
    PATH_PLAYLOG_SESSIONS,
    PATH_PLAYLOG_STATUS,
    PATH_PLAYLOG_SUMMARY,
    PATH_REBOOT,
    PATH_REMOTE_LOG,
    PATH_RESTART_REMOTE,
    PATH_SCREEN,
    PATH_SCREENSHOTS,
    PATH_SCRIPTS_CONSOLE,
    PATH_SCRIPTS_KILL,
    PATH_SCRIPTS_LAUNCH,
    PATH_SCRIPTS_LIST,
    PATH_SEARCH_SYSTEMS,
    PATH_SYSINFO,
    PATH_SYSTEMS,
    PATH_WALLPAPERS,
)

_LOGGER = logging.getLogger(__name__)


class MisterConnectionError(Exception):
    """Raised when the MiSTer Remote API is unreachable or returns an error.

    This exception wraps ``aiohttp.ClientError``, ``TimeoutError``, and
    invalid-JSON responses so callers have a single exception type to catch.
    """


class MisterUnsupportedError(MisterConnectionError):
    """The endpoint does not exist on this Remote version.

    mrext Remote answers unknown ``/api`` routes (or a wrong HTTP method) with
    its web UI, ``200 text/html``, instead of a 404.
    """


def _seg(value: str) -> str:
    """Quote one URL path segment (names may contain ``#``, ``?``, spaces)."""
    return quote(str(value), safe="")


def _safe_relative(path: str) -> str:
    """Reject paths that climb out of the SD card.

    Remote 0.4 joins relative paths onto ``/media/fat`` without containment,
    so ``../..`` reaches the whole filesystem.
    """
    if ".." in path.replace("\\", "/").split("/"):
        raise ValueError(f"path may not contain '..': {path!r}")
    return path


@dataclass
class MisterStatus:
    """Snapshot of the MiSTer device state at a point in time.

    Returned by :meth:`MisterClient.async_get_status` and mutated in-place by
    :func:`~mister_fpga.apply_ws_message`.

    Attributes:
        online: ``True`` when the API responded successfully.
        core: Short core identifier (e.g. ``"SNES"``), or ``None`` when the
            menu is active.
        system: System slug used by mrext (e.g. ``"snes"``).
        system_name: Human-readable system name (e.g. ``"Super Nintendo"``).
        game: Running game as ``"<systemId>/<filename>"`` (or the bare core
            name for arcade), or ``None``.  This is *not* a filesystem path;
            do not pass it to :meth:`MisterClient.async_launch_game`.
        game_name: Basename of the game without extension, or ``None``.
        hostname: MiSTer hostname as reported by the Remote API.
        version: mrext Remote version string.
        ip: Primary IP address of the MiSTer device.
        ips: All IP addresses reported by the device.
        updated: ISO-8601 timestamp of the last sysinfo update.
        updated: Time of the last MiSTer update, not of this snapshot.
        dns: ``<hostname>.local`` mDNS name (only when mDNS is enabled) — not a
            DNS server.
        disk_total: Total SD-card space in bytes.
        disk_used: Used SD-card space in bytes.
        disk_free: Free SD-card space in bytes.
        disks: Every disk reported by sysinfo (SD card, USB drives, ...).
        core_session_time: Seconds the current core has been running
            (Remote >= 0.5, else ``None``).
        game_session_time: Seconds the current game has been running
            (Remote >= 0.5, else ``None``).
    """

    online: bool = False
    core: str | None = None
    system: str | None = None
    system_name: str | None = None
    game: str | None = None
    game_name: str | None = None
    hostname: str | None = None
    version: str | None = None
    ip: str | None = None
    ips: list[str] = field(default_factory=list)
    updated: str | None = None
    dns: str | None = None
    disk_total: int | None = None
    disk_used: int | None = None
    disk_free: int | None = None
    disks: list[dict[str, Any]] = field(default_factory=list)
    core_session_time: int | None = None
    game_session_time: int | None = None

    @property
    def is_running_game(self) -> bool:
        """True when a real core/game (not the menu) is running."""
        if not self.online:
            return False
        core = (self.core or "").strip().lower()
        return bool(core) and core not in ("menu", "none")


class MisterClient:
    """Async REST client for the MiSTer FPGA mrext Remote API.

    Wraps every endpoint exposed by the mrext Remote service under
    ``http://host:port/api``.  All network I/O is non-blocking; methods raise
    :class:`MisterConnectionError` on any network or HTTP error.

    Args:
        host: IP address or hostname of the MiSTer device.
        port: mrext Remote port (default ``8182``).
        session: Optional shared ``aiohttp.ClientSession``.  When ``None`` the
            client creates and owns its own session; call
            :meth:`async_close` to release it.
        timeout: Per-request timeout in seconds (default ``10``).
    """

    def __init__(
        self,
        host: str,
        port: int = 8182,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/api"
        self._timeout = timeout
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def async_close(self) -> None:
        """Close the underlying HTTP session if this client created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        parse_json: bool = True,
    ) -> Any:
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.request(
                method,
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                if not parse_json:
                    return await resp.read()
                if resp.content_type == "text/html":
                    raise MisterUnsupportedError(
                        f"{method} {url} is not an API endpoint on this Remote"
                    )
                text = await resp.text()
                if not text.strip():
                    return None
                try:
                    return json.loads(text)
                except json.JSONDecodeError as err:
                    raise MisterConnectionError(
                        f"{method} {url} returned invalid JSON: {err}"
                    ) from err
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.debug("Request %s %s failed: %s", method, url, err)
            raise MisterConnectionError(f"{method} {url} failed: {err}") from err

    async def async_get_status(self) -> MisterStatus:
        """Fetch a combined sysinfo + playing snapshot.

        Returns:
            A :class:`MisterStatus` with ``online=True`` on success.

        Raises:
            MisterConnectionError: If either underlying request fails.
        """
        sysinfo = await self._request("GET", PATH_SYSINFO) or {}
        playing = await self._request("GET", PATH_PLAYING) or {}
        ips = sysinfo.get("ips") or []
        disks = sysinfo.get("disks") or []
        disk = next(
            (d for d in disks if d.get("path") == "/media/fat"),
            disks[0] if disks else {},
        )
        return MisterStatus(
            online=True,
            core=playing.get("core") or None,
            system=playing.get("system") or None,
            system_name=playing.get("systemName") or None,
            game=playing.get("game") or None,
            game_name=playing.get("gameName") or None,
            hostname=sysinfo.get("hostname"),
            version=sysinfo.get("version"),
            ips=ips,
            ip=ips[0] if ips else None,
            updated=sysinfo.get("updated"),
            dns=sysinfo.get("dns"),
            disk_total=disk.get("total"),
            disk_used=disk.get("used"),
            disk_free=disk.get("free"),
            disks=disks,
            core_session_time=playing.get("coreSessionTime"),
            game_session_time=playing.get("gameSessionTime"),
        )

    async def async_get_systems(self) -> list[dict[str, Any]]:
        """Return the list of systems known to mrext."""
        return await self._request("GET", PATH_SYSTEMS) or []

    async def async_launch_system(self, system_id: str) -> None:
        """Launch the default game/core for *system_id*."""
        await self._request("POST", f"{PATH_SYSTEMS}/{system_id}")

    async def async_launch_game(self, path: str) -> None:
        """Launch a game by its absolute path on the MiSTer SD card."""
        await self._request("POST", PATH_GAMES_LAUNCH, payload={"path": path})

    async def async_launch_menu(self) -> None:
        """Return to the MiSTer main menu."""
        await self._request("POST", PATH_LAUNCH_MENU)

    async def async_search_games(
        self, query: str, system: str = "all", page: int | None = None
    ) -> dict[str, Any]:
        """Search the game index.

        Args:
            query: Free-text search string.
            system: Limit results to a system id, or ``"all"`` (default).
            page: 1-based result page (Remote >= 0.5 paginates; 0.4 ignores it
                and caps results at 500).

        Returns:
            ``{"data": [{"system": {...}, "name", "path"}], "total",
            "pageSize", "page"}``.
        """
        payload: dict[str, Any] = {"query": query, "system": system}
        if page is not None:
            payload["page"] = page
        return await self._request("POST", PATH_GAMES_SEARCH, payload=payload) or {}

    async def async_get_search_systems(self) -> list[dict[str, Any]]:
        """Return the systems present in the game index (``[{id, name}]``)."""
        data = await self._request("GET", PATH_SEARCH_SYSTEMS) or {}
        return data.get("systems", []) if isinstance(data, dict) else []

    async def async_browse_games(self, path: str | None = None) -> dict[str, Any]:
        """List a games folder (``{"up", "items"}``); root when *path* is None."""
        payload = {"path": _safe_relative(path)} if path else {}
        return await self._request("POST", PATH_GAMES_VIEW, payload=payload) or {}

    async def async_browse_menu(self, path: str = "") -> dict[str, Any]:
        """List a folder of the MiSTer menu tree (``{"up", "items": [...]}``).

        Raises:
            ValueError: If *path* contains ``..`` (Remote 0.4 does not contain it).
        """
        return (
            await self._request(
                "POST", PATH_MENU_VIEW, payload={"path": _safe_relative(path)}
            )
            or {}
        )

    async def async_index_games(self) -> None:
        """Trigger a background re-index of the game library."""
        await self._request("POST", PATH_GAMES_INDEX)

    async def async_send_keyboard(self, name: str) -> None:
        """Send a named virtual-keyboard event (see ``KEYBOARD_NAMES``)."""
        await self._request("POST", f"{PATH_KEYBOARD}/{name}")

    async def async_reboot(self) -> None:
        """Reboot the MiSTer device."""
        await self._request("POST", PATH_REBOOT)

    async def async_restart_remote(self) -> None:
        """Restart the mrext Remote service on the MiSTer."""
        await self._request("POST", PATH_RESTART_REMOTE)

    async def async_take_screenshot(self) -> None:
        """Capture a screenshot on the MiSTer and save it server-side."""
        await self._request("POST", PATH_SCREENSHOTS)

    async def async_get_screenshots(self) -> list[dict[str, Any]]:
        """Return metadata for all saved screenshots."""
        data = await self._request("GET", PATH_SCREENSHOTS)
        return data if isinstance(data, list) else []

    async def async_get_screenshot_image(self, core: str, filename: str) -> bytes:
        """Download a screenshot image as raw bytes.

        Args:
            core: Core name sub-directory (e.g. ``"SNES"``).
            filename: Screenshot filename within that sub-directory.

        Returns:
            Raw image bytes (typically PNG).

        Raises:
            MisterConnectionError: If the image cannot be retrieved.
        """
        return await self._request(  # type: ignore[no-any-return]
            "GET", f"{PATH_SCREENSHOTS}/{_seg(core)}/{_seg(filename)}", parse_json=False
        )

    async def async_delete_screenshot(self, core: str, filename: str) -> None:
        """Delete one saved screenshot."""
        await self._request(
            "DELETE", f"{PATH_SCREENSHOTS}/{_seg(core)}/{_seg(filename)}"
        )

    async def async_get_music_status(self) -> dict[str, Any]:
        """Return the current music-player status dict."""
        return await self._request("GET", PATH_MUSIC_STATUS) or {}

    async def async_music_play(self) -> None:
        """Start or resume music playback."""
        await self._request("POST", PATH_MUSIC_PLAY)

    async def async_music_stop(self) -> None:
        """Stop music playback."""
        await self._request("POST", PATH_MUSIC_STOP)

    async def async_music_next(self) -> None:
        """Skip to the next track."""
        await self._request("POST", PATH_MUSIC_NEXT)

    # --- Wallpapers ---
    async def async_get_wallpapers(self) -> dict[str, Any]:
        """Return available wallpapers and the currently active one."""
        return await self._request("GET", PATH_WALLPAPERS) or {}

    async def async_set_wallpaper(self, filename: str) -> None:
        """Set the active wallpaper by filename."""
        await self._request("POST", f"{PATH_WALLPAPERS}/{_seg(filename)}")

    async def async_clear_wallpaper(self) -> None:
        """Remove the active wallpaper (revert to default)."""
        await self._request("DELETE", PATH_WALLPAPERS)

    # --- INI files ---
    async def async_get_inis(self) -> dict[str, Any]:
        """Return a list of MiSTer.ini profiles and the active index."""
        return await self._request("GET", PATH_INIS) or {}

    async def async_get_ini_values(self, ini_id: int) -> dict[str, Any]:
        """Return all key/value pairs for INI profile *ini_id*."""
        return await self._request("GET", f"{PATH_INIS}/{ini_id}") or {}

    async def async_set_active_ini(self, ini_id: int) -> None:
        """Switch the active MiSTer.ini profile to *ini_id*."""
        await self._request("PUT", PATH_INIS, payload={"ini": ini_id})

    async def async_set_ini_values(self, ini_id: int, values: dict[str, Any]) -> None:
        """Update key/value pairs in INI profile *ini_id*."""
        await self._request("PUT", f"{PATH_INIS}/{ini_id}", payload=values)

    async def async_set_background_mode(self, mode: int) -> None:
        """Set the menu background mode.

        Args:
            mode: One of :data:`~mister_fpga.const.BACKGROUND_MODES` (0 none,
                2 wallpaper, 4/6 horizontal bars, 8/10 vertical bars,
                12 spectrum, 14 black).

        Raises:
            ValueError: For any other value (the server rejects odd modes).
        """
        if mode not in BACKGROUND_MODES:
            raise ValueError(f"invalid background mode {mode}")
        await self._request("PUT", PATH_CORE_MENU, payload={"mode": mode})

    # --- Music (extended) ---
    async def async_get_music_playlists(self) -> list[str]:
        """Return the list of available music playlist names."""
        return await self._request("GET", PATH_MUSIC_PLAYLIST) or []

    async def async_set_music_playlist(self, name: str) -> None:
        """Activate the music playlist identified by *name*."""
        await self._request("POST", f"{PATH_MUSIC_PLAYLIST}/{_seg(name)}")

    async def async_set_music_playback(self, mode: str) -> None:
        """Set playback mode (e.g. ``"random"``, ``"loop"``)."""
        await self._request("POST", f"{PATH_MUSIC_PLAYBACK}/{_seg(mode)}")

    # --- Scripts ---
    async def async_get_scripts(self) -> dict[str, Any]:
        """Return the list of user scripts available on the MiSTer."""
        return await self._request("GET", PATH_SCRIPTS_LIST) or {}

    async def async_launch_script(self, filename: str) -> None:
        """Launch a user script by its filename."""
        await self._request("POST", f"{PATH_SCRIPTS_LAUNCH}/{_seg(filename)}")

    async def async_open_console(self) -> None:
        """Open the MiSTer console (script terminal)."""
        await self._request("POST", PATH_SCRIPTS_CONSOLE)

    async def async_kill_script(self) -> None:
        """Kill the currently running user script."""
        await self._request("POST", PATH_SCRIPTS_KILL)

    # --- Peers ---
    async def async_get_peers(self) -> list[dict[str, Any]]:
        """Return the list of mrext Remote peers on the local network."""
        data = await self._request("GET", PATH_PEERS) or {}
        return data.get("peers", [])  # type: ignore[no-any-return]

    # --- Launchers ---
    async def async_launch_path(self, path: str) -> None:
        """Launch a file (ROM, core, script) by its absolute SD-card path."""
        await self._request("POST", PATH_LAUNCH, payload={"path": path})

    async def async_launch_token(self, data: str) -> None:
        """Launch a token: a path, or a ``**command:`` such as ``**random:snes``.

        The text is base64url-encoded (no padding) as the ``/l/<data>``
        endpoint requires; pass it in plain form.
        """
        encoded = base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
        await self._request("GET", f"{PATH_LAUNCH_TOKEN}/{encoded}")

    async def async_create_shortcut(
        self, game_path: str, folder: str, name: str
    ) -> dict[str, Any]:
        """Create a game shortcut in the Favourites/Recents folder.

        Args:
            game_path: Absolute path to the game ROM on the SD card.
            folder: Target folder name (e.g. ``"_Favorites"``).
            name: Display name for the shortcut.

        Returns:
            A dict describing the created shortcut entry.
        """
        return (
            await self._request(
                "POST",
                PATH_LAUNCH_NEW,
                payload={"gamePath": game_path, "folder": folder, "name": name},
            )
            or {}
        )

    # --- Raw keyboard ---
    async def async_send_keyboard_raw(self, code: int) -> None:
        """Tap a Linux evdev ``KEY_*`` code (e.g. 28 = Enter).

        A negative code sends Shift + ``abs(code)``.
        """
        await self._request("POST", f"{PATH_KEYBOARD_RAW}/{code}")

    # --- Remote >= 0.5 ---
    async def async_get_screen(self) -> dict[str, Any]:
        """Return the current framebuffer resolution ``{width, height}``."""
        return await self._request("GET", PATH_SCREEN) or {}

    async def async_get_playlog_status(self) -> dict[str, Any]:
        """PlayLog state: ``{installed, running, database, recents, startup}``."""
        return await self._request("GET", PATH_PLAYLOG_STATUS) or {}

    async def async_get_playlog_summary(
        self, *, top: int | None = None, days: int | None = None
    ) -> dict[str, Any]:
        """Play-time summary: totals (seconds), streaks, top games/systems, per-day."""
        params = "&".join(
            f"{k}={v}" for k, v in (("top", top), ("days", days)) if v is not None
        )
        path = PATH_PLAYLOG_SUMMARY + (f"?{params}" if params else "")
        return await self._request("GET", path) or {}

    async def async_get_playlog_games(
        self, *, sort: str | None = None, limit: int | None = None, offset: int = 0
    ) -> dict[str, Any]:
        """Per-game play stats ``{"games": [...], "total"}``."""
        params = [f"offset={offset}"]
        if sort:
            params.append(f"sort={_seg(sort)}")
        if limit:
            params.append(f"limit={limit}")
        return (
            await self._request("GET", f"{PATH_PLAYLOG_GAMES}?{'&'.join(params)}") or {}
        )

    async def async_get_playlog_sessions(
        self, *, limit: int | None = None, offset: int = 0
    ) -> dict[str, Any]:
        """Recent play sessions ``{"sessions": [...], "total"}``."""
        params = f"offset={offset}" + (f"&limit={limit}" if limit else "")
        return await self._request("GET", f"{PATH_PLAYLOG_SESSIONS}?{params}") or {}

    async def async_get_remote_log(self) -> bytes:
        """Download the Remote service log."""
        return await self._request("GET", PATH_REMOTE_LOG, parse_json=False)  # type: ignore[no-any-return]
