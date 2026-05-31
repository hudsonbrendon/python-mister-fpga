"""Async REST client for the MiSTer FPGA mrext Remote API."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import (
    PATH_CORE_MENU,
    PATH_GAMES_INDEX,
    PATH_GAMES_LAUNCH,
    PATH_GAMES_SEARCH,
    PATH_INIS,
    PATH_KEYBOARD,
    PATH_KEYBOARD_RAW,
    PATH_LAUNCH,
    PATH_LAUNCH_MENU,
    PATH_LAUNCH_NEW,
    PATH_LAUNCH_TOKEN,
    PATH_MUSIC_NEXT,
    PATH_MUSIC_PLAY,
    PATH_MUSIC_PLAYBACK,
    PATH_MUSIC_PLAYLIST,
    PATH_MUSIC_STATUS,
    PATH_MUSIC_STOP,
    PATH_PEERS,
    PATH_PLAYING,
    PATH_REBOOT,
    PATH_RESTART_REMOTE,
    PATH_SCREENSHOTS,
    PATH_SCRIPTS_CONSOLE,
    PATH_SCRIPTS_KILL,
    PATH_SCRIPTS_LAUNCH,
    PATH_SCRIPTS_LIST,
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
        game: Full path of the running game ROM, or ``None``.
        game_name: Basename of the game without extension, or ``None``.
        hostname: MiSTer hostname as reported by the Remote API.
        version: mrext Remote version string.
        ip: Primary IP address of the MiSTer device.
        ips: All IP addresses reported by the device.
        updated: ISO-8601 timestamp of the last sysinfo update.
        dns: DNS server address reported by the device.
        disk_total: Total SD-card space in bytes (first disk).
        disk_used: Used SD-card space in bytes (first disk).
        disk_free: Free SD-card space in bytes (first disk).
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
        payload: dict | None = None,
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
        disk = disks[0] if disks else {}
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
        )

    async def async_get_systems(self) -> list[dict]:
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

    async def async_search_games(self, query: str, system: str = "all") -> dict:
        """Search the game index.

        Args:
            query: Free-text search string.
            system: Limit results to a system slug, or ``"all"`` (default).

        Returns:
            A dict with a ``results`` key containing matching game entries.
        """
        return (
            await self._request(
                "POST", PATH_GAMES_SEARCH, payload={"data": query, "system": system}
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

    async def async_get_screenshots(self) -> list[dict]:
        """Return metadata for all saved screenshots."""
        return await self._request("GET", PATH_SCREENSHOTS) or []

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
        return await self._request(
            "GET", f"{PATH_SCREENSHOTS}/{core}/{filename}", parse_json=False
        )

    async def async_get_music_status(self) -> dict:
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
    async def async_get_wallpapers(self) -> dict:
        """Return available wallpapers and the currently active one."""
        return await self._request("GET", PATH_WALLPAPERS) or {}

    async def async_set_wallpaper(self, filename: str) -> None:
        """Set the active wallpaper by filename."""
        await self._request("POST", f"{PATH_WALLPAPERS}/{filename}")

    async def async_clear_wallpaper(self) -> None:
        """Remove the active wallpaper (revert to default)."""
        await self._request("DELETE", PATH_WALLPAPERS)

    # --- INI files ---
    async def async_get_inis(self) -> dict:
        """Return a list of MiSTer.ini profiles and the active index."""
        return await self._request("GET", PATH_INIS) or {}

    async def async_get_ini_values(self, ini_id: int) -> dict:
        """Return all key/value pairs for INI profile *ini_id*."""
        return await self._request("GET", f"{PATH_INIS}/{ini_id}") or {}

    async def async_set_active_ini(self, ini_id: int) -> None:
        """Switch the active MiSTer.ini profile to *ini_id*."""
        await self._request("PUT", PATH_INIS, payload={"ini": ini_id})

    async def async_set_ini_values(self, ini_id: int, values: dict) -> None:
        """Update key/value pairs in INI profile *ini_id*."""
        await self._request("PUT", f"{PATH_INIS}/{ini_id}", payload=values)

    async def async_set_background_mode(self, mode: int) -> None:
        """Set the core/menu background display mode (0 = off, 1 = wallpaper, …)."""
        await self._request("PUT", PATH_CORE_MENU, payload={"mode": mode})

    # --- Music (extended) ---
    async def async_get_music_playlists(self) -> list[str]:
        """Return the list of available music playlist names."""
        return await self._request("GET", PATH_MUSIC_PLAYLIST) or []

    async def async_set_music_playlist(self, name: str) -> None:
        """Activate the music playlist identified by *name*."""
        await self._request("POST", f"{PATH_MUSIC_PLAYLIST}/{name}")

    async def async_set_music_playback(self, mode: str) -> None:
        """Set playback mode (e.g. ``"random"``, ``"loop"``)."""
        await self._request("POST", f"{PATH_MUSIC_PLAYBACK}/{mode}")

    # --- Scripts ---
    async def async_get_scripts(self) -> dict:
        """Return the list of user scripts available on the MiSTer."""
        return await self._request("GET", PATH_SCRIPTS_LIST) or {}

    async def async_launch_script(self, filename: str) -> None:
        """Launch a user script by its filename."""
        await self._request("POST", f"{PATH_SCRIPTS_LAUNCH}/{filename}")

    async def async_open_console(self) -> None:
        """Open the MiSTer console (script terminal)."""
        await self._request("POST", PATH_SCRIPTS_CONSOLE)

    async def async_kill_script(self) -> None:
        """Kill the currently running user script."""
        await self._request("POST", PATH_SCRIPTS_KILL)

    # --- Peers ---
    async def async_get_peers(self) -> list[dict]:
        """Return the list of mrext Remote peers on the local network."""
        data = await self._request("GET", PATH_PEERS) or {}
        return data.get("peers", [])

    # --- Launchers ---
    async def async_launch_path(self, path: str) -> None:
        """Launch a file (ROM, core, script) by its absolute SD-card path."""
        await self._request("POST", PATH_LAUNCH, payload={"path": path})

    async def async_launch_token(self, data: str) -> None:
        """Launch using a short-link token (mrext ``/l/<data>`` endpoint)."""
        await self._request("GET", f"{PATH_LAUNCH_TOKEN}/{data}")

    async def async_create_shortcut(
        self, game_path: str, folder: str, name: str
    ) -> dict:
        """Create a game shortcut in the Favourites/Recents folder.

        Args:
            game_path: Absolute path to the game ROM on the SD card.
            folder: Target folder name (e.g. ``"_Favorites"``).
            name: Display name for the shortcut.

        Returns:
            A dict describing the created shortcut entry.
        """
        return await self._request(
            "POST",
            PATH_LAUNCH_NEW,
            payload={"gamePath": game_path, "folder": folder, "name": name},
        ) or {}

    # --- Raw keyboard ---
    async def async_send_keyboard_raw(self, code: int) -> None:
        """Send a raw HID keyboard scan-code integer."""
        await self._request("POST", f"{PATH_KEYBOARD_RAW}/{code}")
