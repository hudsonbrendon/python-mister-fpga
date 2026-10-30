"""WebSocket client for real-time MiSTer Remote updates."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
import logging

import aiohttp

from .client import MisterStatus
from .const import WS_PATH

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MisterIndexStatus:
    """Game-index state carried by ``indexStatus:`` frames."""

    exists: bool = False
    indexing: bool = False
    total_steps: int = 0
    current_step: int = 0
    description: str = ""


def parse_index_status(rest: str) -> MisterIndexStatus:
    """Parse the payload of ``indexStatus:<y|n>,<y|n>,<total>,<current>,<desc>``."""
    parts = rest.split(",", 4)
    parts += [""] * (5 - len(parts))

    def _int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    return MisterIndexStatus(
        exists=parts[0] == "y",
        indexing=parts[1] == "y",
        total_steps=_int(parts[2]),
        current_step=_int(parts[3]),
        description=parts[4],
    )


def split_menu_navigation(rest: str) -> tuple[str | None, str | None]:
    """Split ``menuNavigation:<FULLPATH>:<CURRENTPATH>`` into its two parts.

    *FULLPATH* is the folder open in the menu, *CURRENTPATH* the highlighted
    entry.  Older senders without the separator yield ``(rest, None)``.
    """
    full, sep, current = rest.strip().partition(":")
    if not sep:
        return full or None, None
    return full or None, current or None


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

    * ``coreRunning`` — updates :attr:`~mister_fpga.MisterStatus.core`;
      switching from another core clears the stale system and game fields
      (a launch from the menu sends ``gameRunning`` first, so that is kept).
    * ``gameRunning`` — updates :attr:`~mister_fpga.MisterStatus.game` and
      :attr:`~mister_fpga.MisterStatus.game_name` (``<system>/<file>``, or the
      bare core name for arcade).
    * ``menuNavigation`` — updates *menu_path* to ``FULLPATH/CURRENTPATH``
      (see :func:`split_menu_navigation` for the parts).
    * ``indexStatus`` — updates *index_state* ``(exists, in_progress)``; use
      :func:`parse_index_status` for the progress fields.

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
        if core == status.core:
            return status, menu_path, index_state
        if status.core is None:
            # On launch mrext sends gameRunning before coreRunning; keep the game.
            return replace(status, core=core), menu_path, index_state
        return (
            replace(
                status,
                core=core,
                system=None,
                system_name=None,
                game=None,
                game_name=None,
            ),
            menu_path,
            index_state,
        )
    if prefix == "gameRunning":
        rest = rest.strip()
        if not rest:
            return replace(status, game=None, game_name=None), menu_path, index_state
        _, sep, name = rest.partition("/")
        if not sep:  # arcade: the bare core/MRA name
            name = rest
        game_name = name.rsplit(".", 1)[0] if sep else name
        return replace(status, game=rest, game_name=game_name), menu_path, index_state
    if prefix == "menuNavigation":
        full, current = split_menu_navigation(rest)
        path = "/".join(p for p in (full, current) if p) or None
        return status, path, index_state
    if prefix == "indexStatus":
        idx = parse_index_status(rest)
        return status, menu_path, (idx.exists, idx.indexing)
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
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    @property
    def url(self) -> str:
        """Full WebSocket URL derived from *host* and *port*."""
        return f"ws://{self.host}:{self.port}{WS_PATH}"

    async def listen(
        self,
        on_message: Callable[[str], Awaitable[None] | None],
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
                        self._ws = ws
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                result = on_message(msg.data)
                                if isinstance(result, Awaitable):
                                    await result
                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break
                except (aiohttp.ClientError, TimeoutError):
                    pass
                finally:
                    self._ws = None
                if self._stop:
                    break  # type: ignore[unreachable]
                await asyncio.sleep(self._reconnect_delay)
        finally:
            if owns:
                await session.close()

    @property
    def connected(self) -> bool:
        """True while a WebSocket connection is open."""
        return self._ws is not None and not self._ws.closed

    async def async_send(self, message: str) -> None:
        """Send a raw command frame on the open connection.

        Server commands: ``getIndexStatus``, ``kbd:<name>``, ``kbdRaw:<code>``,
        ``kbdRawDown:<code>`` / ``kbdRawUp:<code>`` (hold a key), and on
        Remote >= 0.5 ``mouseMove``/``mousePos``/``mouseBtn``.  Unknown
        commands are answered with an ``invalid`` frame.

        Raises:
            ConnectionError: If not connected.
        """
        ws = self._ws
        if ws is None or ws.closed:
            raise ConnectionError("MiSTer WebSocket is not connected")
        await ws.send_str(message)

    def stop(self) -> None:
        """Signal the :meth:`listen` loop to exit after the current iteration."""
        self._stop = True
