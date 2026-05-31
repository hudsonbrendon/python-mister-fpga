"""WebSocket client for real-time MiSTer Remote updates."""
from __future__ import annotations

import asyncio
import logging
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
    """Pure reducer: apply one WS text frame to (status, menu_path, index_state)."""
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
    """Connects to the mrext Remote WebSocket and invokes a callback per text frame."""

    def __init__(
        self,
        host: str,
        port: int = 8182,
        *,
        session=None,
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
        return f"ws://{self.host}:{self.port}{WS_PATH}"

    async def listen(self, on_message) -> None:
        """Run the reconnect loop, calling on_message(text) for each TEXT frame.

        on_message may be sync or async. Runs until stop() or cancellation.
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
        self._stop = True
