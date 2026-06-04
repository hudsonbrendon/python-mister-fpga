"""RetroAchievements local control over SSH (best-effort)."""
from __future__ import annotations

import logging
import re

from .const import RA_USERNAME_PLACEHOLDER, MisterRAStatus

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
