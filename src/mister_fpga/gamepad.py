"""Virtual gamepad/keyboard via the MiSTer Companion Remote daemon.

The daemon (``companion_remote.sh`` by Anime0t4ku, port 9191) creates uinput
devices on the MiSTer, so presses look like a real USB controller to every
core, the menu and MiSTer_SAM — unlike mrext's keyboard API, which only sends
keys.  It serves one WebSocket client at a time and releases everything held
when that client disconnects, so this client connects per call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any, TypeVar

import aiohttp

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")

DEFAULT_GAMEPAD_PORT = 9191
DEFAULT_GAMEPAD_PATH = "/remote/v1"

GAMEPAD_BUTTONS = (
    "a",
    "b",
    "x",
    "y",
    "l",
    "r",
    "select",
    "start",
    "home",
    "up",
    "down",
    "left",
    "right",
)
GAMEPAD_ACTIONS = ("tap", "down", "up")


class MisterGamepadError(Exception):
    """The daemon is unreachable or rejected a command."""


class MisterGamepad:
    """Client for the Companion Remote virtual controller.

    Args:
        host: MiSTer IP or hostname.
        port: Daemon port (default 9191).
        path: WebSocket path (default ``/remote/v1``).
        session: Optional shared ``aiohttp.ClientSession``.
        timeout: Seconds for the whole exchange (connect + replies).
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_GAMEPAD_PORT,
        path: str = DEFAULT_GAMEPAD_PATH,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 5,
    ) -> None:
        self.url = f"ws://{host}:{port}{path}"
        self.status_url = f"http://{host}:{port}/status"
        self._session = session
        self._timeout = timeout

    async def _with_session(
        self, func: Callable[[aiohttp.ClientSession], Awaitable[_T]]
    ) -> _T:
        if self._session is not None:
            return await func(self._session)
        async with aiohttp.ClientSession() as session:
            return await func(session)

    async def async_available(self) -> bool:
        """True when the daemon answers ``GET /status``."""

        async def _probe(session: aiohttp.ClientSession) -> bool:
            try:
                async with session.get(
                    self.status_url, timeout=aiohttp.ClientTimeout(total=self._timeout)
                ) as resp:
                    return resp.status == 200 and (await resp.json()).get("ok") is True
            except (aiohttp.ClientError, TimeoutError, ValueError):
                return False

        return await self._with_session(_probe)

    async def async_send(self, *commands: dict[str, Any]) -> list[dict[str, Any]]:
        """Send raw daemon commands over one connection and return the replies.

        Raises:
            MisterGamepadError: On connection failure or an ``ok: false`` reply.
        """

        async def _run(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
            replies = []
            try:
                async with (
                    asyncio.timeout(self._timeout),
                    session.ws_connect(self.url) as ws,
                ):
                    await ws.receive_json(timeout=self._timeout)  # hello
                    for command in commands:
                        await ws.send_str(json.dumps(command))
                        reply = await ws.receive_json(timeout=self._timeout)
                        if not reply.get("ok"):
                            raise MisterGamepadError(reply.get("message") or "rejected")
                        replies.append(reply)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise MisterGamepadError(f"{self.url}: {err}") from err
            return replies

        return await self._with_session(_run)

    async def async_press(self, button: str, action: str = "tap") -> None:
        """Press a controller button or D-pad direction.

        Args:
            button: One of :data:`GAMEPAD_BUTTONS`.
            action: ``"tap"`` (45 ms press), ``"down"`` or ``"up"``.  A held
                button is released when the connection closes, so ``down``
                only lasts for the call — use :meth:`async_send` for chords.
        """
        if button not in GAMEPAD_BUTTONS:
            raise ValueError(f"unknown button {button!r}")
        if action not in GAMEPAD_ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        name = "mode" if button == "home" else button
        await self.async_send({"type": "controller", "name": name, "action": action})

    async def async_key(self, key: str, action: str = "tap") -> None:
        """Press a virtual keyboard key by evdev name, e.g. ``"KEY_F12"``."""
        if action not in GAMEPAD_ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        await self.async_send(
            {"type": "keyboard", "key": key.upper(), "action": action}
        )
