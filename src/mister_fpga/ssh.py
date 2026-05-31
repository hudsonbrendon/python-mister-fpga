"""Optional SSH telemetry client for the MiSTer FPGA."""
from __future__ import annotations

import logging

from .const import SSH_PROBE_CMD

_LOGGER = logging.getLogger(__name__)

_SEP = "|||"


def parse_ssh_probe(raw: str) -> dict:
    """Parse the batched SSH probe output into a telemetry dict.

    The probe command (``SSH_PROBE_CMD``) concatenates five fields separated by
    ``|||``: active core name, uptime, load average, memory info, and firmware
    timestamp.  Any missing or malformed field is silently coerced to ``None``.

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
    """
    parts = [p.strip() for p in raw.split(_SEP)]
    while len(parts) < 5:
        parts.append("")
    core, uptime_s, load_s, mem_s, fw_s = parts[:5]

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

    return {
        "active_core": core or None,
        "uptime_seconds": uptime,
        "cpu_load_1m": load_1m,
        "memory_used_percent": mem_used_pct,
        "firmware_timestamp": fw_ts,
    }


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

    async def async_probe(self) -> dict:
        """Run the SSH probe command and return parsed telemetry.

        Returns:
            Telemetry dict as returned by :func:`parse_ssh_probe`, or ``{}``
            if the SSH connection or command fails.
        """
        try:
            await self._ensure()
            result = await self._conn.run(SSH_PROBE_CMD, check=False, timeout=10)
            return parse_ssh_probe(result.stdout or "")
        except Exception as err:  # noqa: BLE001 - asyncssh raises many types; SSH is best-effort and must never break the HTTP integration
            _LOGGER.debug("MiSTer SSH probe failed: %s", err)
            self._conn = None
            return {}

    async def async_close(self) -> None:
        """Close the underlying SSH connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
