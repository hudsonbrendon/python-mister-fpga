"""RetroAchievements local control over SSH (best-effort)."""

from __future__ import annotations

import logging
import re
import shlex
from typing import Any

from .const import RA_STATUS_CMD, RA_USERNAME_PLACEHOLDER, MisterRAStatus
from .ssh import MisterSSH

RA_DEBUG_LOG = "/tmp/ra_debug.log"  # noqa: S108
RA_CFG = "/media/fat/retroachievements.cfg"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LOG_PATTERNS = (
    (
        "login",
        re.compile(
            r"RA: LOGIN OK: (?P<user>.+?) \(hardcore: (?P<hardcore_points>\d+),"
            r" softcore: (?P<softcore_points>\d+)\)"
        ),
    ),
    ("game_id", re.compile(r"RA:\s+ID: (?P<game_id>\d+)")),
    ("game_title", re.compile(r"RA:\s+Title: (?P<title>.+)")),
    (
        "achievement",
        re.compile(
            r"RA: \*\*\* ACHIEVEMENT TRIGGERED: \[(?P<id>\d+)\] (?P<title>.+?)"
            r"(?: [—-] (?P<description>.*?))?(?: \*\*\*)?$"
        ),
    ),
    (
        "leaderboard",
        re.compile(r"RA: LEADERBOARD SUBMITTED: \[(?P<id>\d+)\] (?P<title>.+)"),
    ),
    ("game_completed", re.compile(r"RA: \*\*\* GAME COMPLETED! \*\*\*")),
    ("game_unload", re.compile(r"RA: --- Game Unload ---")),
)


def parse_ra_log(text: str) -> list[dict[str, Any]]:
    """Turn ``/tmp/ra_debug.log`` lines into events.

    odelot's Main only writes this log with ``debug=1`` in
    ``retroachievements.cfg``.  ``game_id`` and ``game_title`` lines follow a
    ``=== GAME IDENTIFIED ===`` header and are merged into one
    ``game_identified`` event.

    Returns:
        Dicts with a ``type`` key (``login``, ``game_identified``,
        ``achievement``, ``leaderboard``, ``game_completed``, ``game_unload``)
        plus the captured fields; numeric fields are ints.
    """
    events: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = _ANSI.sub("", raw).strip()
        for kind, pattern in _LOG_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            data = {
                k: int(v) if v is not None and v.isdigit() else v
                for k, v in match.groupdict().items()
            }
            if kind == "game_id":
                events.append({"type": "game_identified", **data})
            elif kind == "game_title":
                if events and events[-1]["type"] == "game_identified":
                    events[-1].setdefault("title", data["title"])
            else:
                events.append({"type": kind, **data})
            break
    return events


_LOGGER = logging.getLogger(__name__)

# Matches a per-core table row: "NES   RA  -> ..." or "PSX   STOCK  ...".
_CORE_ROW = re.compile(r"^\S+\s+(RA|STOCK)\b")


def parse_ra_status(raw: str) -> MisterRAStatus:
    """Parse RA_STATUS_CMD output into a MisterRAStatus.

    Tolerant of format drift: matches stable prefixes, ignores unknown lines,
    and never raises.
    """
    status = MisterRAStatus()
    total = 0
    active = 0
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("installed="):
            status.installed = stripped.split("=", 1)[1].strip() == "1"
        elif stripped.startswith("username="):
            value = stripped.split("=", 1)[1].strip()
            status.username = (
                value if value and value != RA_USERNAME_PLACEHOLDER else None
            )
        elif stripped.startswith("Mode flag:"):
            status.cores_on = "ON" in stripped.split(":", 1)[1]
        elif stripped.startswith("Hardcore"):
            status.hardcore = "ON" in stripped.split(":", 1)[1]
        elif stripped.startswith("/media/fat/MiSTer"):
            status.binary_ra = "RA" in stripped.split(":", 1)[1]
        else:
            match = _CORE_ROW.match(line)
            if match:
                total += 1
                if match.group(1) == "RA":
                    active += 1
    status.cores_total = total
    status.cores_active = active
    return status


class MisterRAError(Exception):
    """A RetroAchievements control command failed."""


class MisterRA:
    """RetroAchievements local control sharing a MisterSSH connection."""

    def __init__(self, ssh: MisterSSH) -> None:
        self._ssh = ssh

    async def async_status(self) -> MisterRAStatus | None:
        """Probe RA state. Returns None only on SSH failure (best-effort)."""
        try:
            _rc, out = await self._ssh.async_run(RA_STATUS_CMD, timeout=15)
        except Exception as err:  # noqa: BLE001 - best-effort; never break the integration
            _LOGGER.debug("RA status probe failed: %s", err)
            return None
        return parse_ra_status(out)

    async def async_cores_on(self) -> None:
        """Enable RetroAchievements in the supported cores."""
        await self._run_checked("bash /media/fat/Scripts/.ra/ra_on.sh")

    async def async_cores_off(self) -> None:
        """Disable RetroAchievements in the supported cores."""
        await self._run_checked("bash /media/fat/Scripts/.ra/ra_off.sh")

    async def async_set_hardcore(self, enabled: bool) -> None:
        """Turn hardcore mode on or off."""
        arg = "on" if enabled else "off"
        await self._run_checked(f"bash /media/fat/Scripts/.ra/ra_hardcore.sh {arg}")

    async def async_read_log(self, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
        """Read new RA log events written since *offset*.

        Returns:
            ``(new_offset, events)``.  Pass ``new_offset`` back next time.  When
            Main restarts the log is truncated; the offset then resets to 0.
        """
        cmd = (
            f"S=$(stat -c %s {RA_DEBUG_LOG} 2>/dev/null || echo 0); echo $S; "
            f"[ $S -ge {int(offset)} ] && O={int(offset)} || O=0; "
            f"tail -c +$((O+1)) {RA_DEBUG_LOG} 2>/dev/null | head -c 262144"
        )
        _rc, out = await self._ssh.async_run(cmd, timeout=15)
        size_s, _, body = out.partition("\n")
        try:
            size = int(size_s.strip())
        except ValueError:
            return offset, []
        start = offset if size >= offset else 0
        complete = body[: body.rfind("\n") + 1]  # keep partial line
        return start + len(complete.encode()), parse_ra_log(complete)

    async def async_set_debug(self, enabled: bool) -> None:
        """Turn RA debug logging on/off (applies on the next core load)."""
        value = "1" if enabled else "0"
        cfg = shlex.quote(RA_CFG)
        await self._run_checked(
            f"grep -q '^debug=' {cfg} && sed -i 's/^debug=.*/debug={value}/' {cfg}"
            f" || echo 'debug={value}' >> {cfg}"
        )

    async def _run_checked(self, command: str) -> None:
        rc, out = await self._ssh.async_run(command, timeout=30)
        if rc != 0:
            raise MisterRAError(f"command failed (rc={rc}): {command}\n{out}")
