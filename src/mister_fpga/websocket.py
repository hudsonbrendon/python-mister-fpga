"""WebSocket client for real-time MiSTer Remote updates."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace

import aiohttp

from .client import MisterStatus
from .const import WS_PATH

_LOGGER = logging.getLogger(__name__)


def apply_ws_message(
    message: str,
    status: MisterStatus,
    menu_path: str | None,
    index_state: tuple[bool, bool],
) -> tuple[MisterStatus, str | None, tuple[bool, bool]]:
    """Apply one WebSocket text frame to the current state triple.

    This is a *pure* reducer — it never mutates its arguments.  Pass it every
    raw text frame received from :class:`MisterWebSocketClient` to keep a
    local :class:`~mister_fpga.MisterStatus` in sync without polling the REST
    API.

    Understood prefixes (``prefix:rest``):

    * ``coreRunning`` — updates :attr:`~mister_fpga.MisterStatus.core`.
    * ``gameRunning`` — updates :attr:`~mister_fpga.MisterStatus.game` and
      :attr:`~mister_fpga.MisterStatus.game_name`.
    * ``menuNavigation`` — updates *menu_path*.
    * ``indexStatus`` — updates *index_state* ``(exists, in_progress)``.

    Args:
        message: Raw text frame received from the WebSocket.
        status: Current device-state snapshot.
        menu_path: Current menu navigation path, or ``None``.
        index_state: Tuple ``(index_exists, index_in_progress)``.

    Returns:
        A new ``(status, menu_path, index_state)`` triple reflecting the
        change encoded in *message*.  Unrecognised prefixes are passed through
        unchanged.
    """
    prefix, _, rest = message.partition(":")
    if prefix == "coreRunning":
        core = rest.strip() or None
        if core is None:
            return (
                replace(status, core=None, game=None, game_name=None),
                menu_path,
                index_state,
            )
        return replace(status, core=core), menu_path, index_state
    if prefix == "gameRunning":
        rest = rest.strip()
        if not rest:
            return replace(status, game=None, game_name=None), menu_path, index_state
        _, _, name = rest.partition("/")
        game_name = name.rsplit(".", 1)[0] if name else None
        return replace(status, game=rest, game_name=game_name), menu_path, index_state
    if prefix == "menuNavigation":
        return status, rest.strip() or None, index_state
    if prefix == "indexStatus":
        parts = rest.split(",")
        exists = len(parts) > 0 and parts[0] == "y"
        in_progress = len(parts) > 1 and parts[1] == "y"
        return status, menu_path, (exists, in_progress)
    return status, menu_path, index_state


class MisterWebSocketClient:
    """Reconnecting WebSocket client for real-time MiSTer Remote events.

    Connects to the mrext Remote WebSocket endpoint and invokes a callback for
    every TEXT frame received.  If the connection drops the client waits
    *reconnect_delay* seconds and reconnects automatically.

    Args:
        host: IP address or hostname of the MiSTer device.
        port: mrext Remote port (default ``8182``).
        session: Optional shared ``aiohttp.ClientSession``.  When ``None`` the
            client creates and owns its own session.
        reconnect_delay: Seconds to wait before reconnecting after a
            connection loss (default ``5``).
    """

    def __init__(
        self,
        host: str,
        port: int = 8182,
        *,
        session: aiohttp.ClientSession | None = None,
        reconnect_delay: int = 5,
    ) -> None:
        self.host = host
        self.port = port
        self._session = session
        self._owns_session = session is None
        self._reconnect_delay = reconnect_delay
        self._stop = False

    @property
    def url(self) -> str:
        """Full WebSocket URL derived from *host* and *port*."""
        return f"ws://{self.host}:{self.port}{WS_PATH}"

    async def listen(
        self,
        on_message: Callable[[str], None | Awaitable[None]],
    ) -> None:
        """Run the reconnect loop, calling *on_message* for each TEXT frame.

        Blocks until :meth:`stop` is called or the task is cancelled.
        *on_message* may be a plain function or a coroutine function.

        Args:
            on_message: Callable ``(text: str) -> None | Awaitable``.
        """
        owns = self._session is None
        session = self._session or aiohttp.ClientSession()
        try:
            while not self._stop:
                try:
                    async with session.ws_connect(self.url, heartbeat=30) as ws:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                result = on_message(msg.data)
                                if hasattr(result, "__await__"):
                                    await result
                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break
                except (aiohttp.ClientError, TimeoutError):
                    pass
                if self._stop:
                    break
                await asyncio.sleep(self._reconnect_delay)
        finally:
            if owns:
                await session.close()

    def stop(self) -> None:
        """Signal the :meth:`listen` loop to exit after the current iteration."""
        self._stop = True
