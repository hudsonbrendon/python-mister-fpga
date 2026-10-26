"""Optional SSH telemetry client for the MiSTer FPGA."""
from __future__ import annotations

import asyncio
import logging
import shlex

from .const import CMD_FIFO, SSH_PROBE_CMD

_LOGGER = logging.getLogger(__name__)

_SEP = "|||"

# Runs on the MiSTer: one non-blocking write (<= PIPE_BUF, so all-or-EAGAIN).
_FIFO_WRITE_PY = (
    "import os,sys\n"
    "try:\n"
    f" f=os.open('{CMD_FIFO}',os.O_WRONLY|os.O_NONBLOCK)\n"
    " os.write(f,sys.argv[1].encode()+b'\\n')\n"
    "except OSError as e:\n"
    " print(e); sys.exit(3)\n"
)


def parse_ssh_probe(raw: str) -> dict:
    """Parse the batched SSH probe output into a telemetry dict.

    The probe command (``SSH_PROBE_CMD``) concatenates eleven fields separated
    by ``|||``.  Any missing or malformed field is silently coerced to
    ``None``, so output from an older probe still parses.

    Args:
        raw: Raw stdout string returned by running ``SSH_PROBE_CMD`` on the
            MiSTer over SSH.

    Returns:
        A dict with the following keys:

        * ``active_core`` (``str | None``) — name from ``/tmp/CORENAME``.
        * ``uptime_seconds`` (``int | None``) — seconds since last boot.
        * ``cpu_load_1m`` (``float | None``) — 1-minute load average.
        * ``memory_used_percent`` (``float | None``) — RAM usage 0–100.
        * ``firmware_timestamp`` (``int | None``) — mtime of the MiSTer binary.
        * ``cmd_fifo_pending`` (``int | None``) — unread command-FIFO bytes.
        * ``main_open_fds`` (``int | None``) — open descriptors of Main.
        * ``volume`` (``int | None``) — 0-7, 7 loudest.
        * ``muted`` (``bool | None``).
        * ``game_id`` (``str | None``) — CRC32 or disc serial of the game.
        * ``sam_active`` (``bool | None``) — Super Attract Mode is cycling.
        * ``sam_game`` (``str | None``) — game SAM shows, e.g. ``Breakers (neogeo)``.

        ``cmd_fifo_pending`` above zero on two probes in a row means Main is
        hung (its loop also drains ``/dev/MiSTer_cmd``).  Some Main builds
        leak one descriptor per core load; the limit is 1024.
    """
    parts = [p.strip() for p in raw.split(_SEP)]
    while len(parts) < 11:
        parts.append("")
    core, uptime_s, load_s, mem_s, fw_s = parts[:5]
    fifo_s, fds_s, vol_s, gameid_s, sam_s, sam_game_s = parts[5:11]

    def _int(value: str) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    uptime = _int(uptime_s.split()[0]) if uptime_s else None
    load_1m = None
    if load_s:
        try:
            load_1m = float(load_s.split()[0])
        except (ValueError, IndexError):
            load_1m = None
    mem_used_pct = None
    mem_lines = [m for m in mem_s.splitlines() if m]
    if len(mem_lines) >= 2:
        total = _int(mem_lines[0])
        avail = _int(mem_lines[1])
        if total:
            mem_used_pct = round((total - avail) / total * 100, 1)
    fw_ts = _int(fw_s) if fw_s else None
    volume, muted = parse_volume(_int(vol_s) if vol_s else None)

    return {
        "active_core": core or None,
        "uptime_seconds": uptime,
        "cpu_load_1m": load_1m,
        "memory_used_percent": mem_used_pct,
        "firmware_timestamp": fw_ts,
        "cmd_fifo_pending": _int(fifo_s) if fifo_s else None,
        "main_open_fds": _int(fds_s) if fds_s else None,
        "volume": volume,
        "muted": muted,
        "game_id": parse_game_id(gameid_s),
        "sam_active": bool(_int(sam_s)) if sam_s else None,
        "sam_game": sam_game_s or None,
    }


class MisterMainUnresponsiveError(Exception):
    """Main_MiSTer is not draining /dev/MiSTer_cmd; the command was not queued."""


def parse_volume(raw: int | None) -> tuple[int | None, bool | None]:
    """Decode ``/media/fat/config/Volume.dat`` into ``(level, muted)``.

    Bits 0-2 hold the attenuation (0 = loudest, 7 = quietest) and bit 4 the
    mute flag. ``level`` is returned the other way round, 0-7 with 7 loudest,
    which is also what the ``volume <n>`` FIFO command expects.
    """
    if raw is None:
        return None, None
    return 7 - (raw & 0x07), bool(raw & 0x10)


def parse_game_id(raw: str) -> str | None:
    """Return the CRC32 or serial from ``/tmp/GAMEID`` (needs log_file_entry=1)."""
    for line in raw.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("CRC32", "Serial") and value.strip():
            return value.strip()
    return None


class MisterSSH:
    """Persistent asyncssh connection for MiSTer telemetry probes.

    Maintains a single SSH connection that is re-established transparently on
    failure.  SSH telemetry is strictly best-effort: :meth:`async_probe`
    always returns a dict (possibly empty) and never raises.

    Args:
        host: IP address or hostname of the MiSTer device.
        port: SSH port (default ``22``).
        username: SSH username (default ``"root"``).
        password: SSH password (often ``"1"`` on stock MiSTer).
    """

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._conn = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._conn is not None:
            return
        import asyncssh

        self._conn = await asyncssh.connect(
            self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            known_hosts=None,
        )

    async def async_run(self, command: str, timeout: int = 15) -> tuple[int, str]:
        """Run a command over the shared SSH connection.

        Returns ``(exit_status, stdout)``. Raises on connection/transport
        failure (callers that need best-effort behaviour must catch).
        """
        async with self._lock:
            try:
                await self._ensure()
                result = await self._conn.run(command, check=False, timeout=timeout)
            except Exception:
                self._conn = None
                raise
            return result.exit_status or 0, result.stdout or ""

    async def async_probe(self) -> dict:
        """Run the SSH probe command and return parsed telemetry."""
        try:
            _rc, out = await self.async_run(SSH_PROBE_CMD, timeout=10)
            return parse_ssh_probe(out)
        except Exception as err:  # noqa: BLE001 - SSH is best-effort; never break the HTTP integration
            _LOGGER.debug("MiSTer SSH probe failed: %s", err)
            return {}

    async def async_send_command(self, command: str) -> None:
        """Queue one command on ``/dev/MiSTer_cmd`` without ever blocking.

        Main reads the FIFO only while its loop is alive, so a plain ``echo``
        hangs forever when Main is stuck.  The write here is non-blocking and
        fails fast instead.

        Args:
            command: e.g. ``"volume 5"``, ``"volume mute"``,
                ``"load_core /media/fat/menu.rbf"``, ``"screenshot"``.

        Raises:
            ValueError: If *command* is empty or contains a newline.
            MisterMainUnresponsiveError: If the FIFO is full or missing.
        """
        if "\n" in command or not command.strip():
            raise ValueError(f"invalid MiSTer command: {command!r}")
        rc, out = await self.async_run(
            f"python3 -c {shlex.quote(_FIFO_WRITE_PY)} {shlex.quote(command)}",
            timeout=10,
        )
        if rc != 0:
            raise MisterMainUnresponsiveError(out.strip() or f"rc={rc}")

    async def async_set_volume(self, level: int) -> None:
        """Set master volume, 0-7 (7 loudest)."""
        if not 0 <= level <= 7:
            raise ValueError("volume must be 0-7")
        await self.async_send_command(f"volume {level}")

    async def async_set_mute(self, muted: bool) -> None:
        """Mute or unmute master audio."""
        await self.async_send_command("volume mute" if muted else "volume unmute")

    async def async_close(self) -> None:
        """Close the underlying SSH connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
