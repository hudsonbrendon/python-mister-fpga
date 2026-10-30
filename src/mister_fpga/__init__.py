"""Async Python client for the MiSTer FPGA mrext Remote API."""

from importlib import metadata

from .client import (
    MisterClient,
    MisterConnectionError,
    MisterStatus,
    MisterUnsupportedError,
)
from .const import (
    BACKGROUND_MODES,
    CMD_FIFO,
    DEFAULT_PORT,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
    INI_VIDEO_KEYS,
    KEYBOARD_NAMES,
    MDNS_SERVICE_TYPE,
    RA_STATUS_CMD,
    RA_SUPPORTED_SYSTEMS,
    RA_USERNAME_PLACEHOLDER,
    SSH_PROBE_CMD,
    WS_PATH,
    MisterRAStatus,
    MisterRAWebStats,
    RAAchievement,
    RAGameProgress,
)
from .gamepad import (
    DEFAULT_GAMEPAD_PATH,
    DEFAULT_GAMEPAD_PORT,
    GAMEPAD_ACTIONS,
    GAMEPAD_BUTTONS,
    MisterGamepad,
    MisterGamepadError,
)
from .ra import MisterRA, MisterRAError, parse_ra_log, parse_ra_status
from .ra_web import MisterRAWeb, MisterRAWebError
from .ssh import (
    MisterMainUnresponsiveError,
    MisterSSH,
    parse_game_id,
    parse_ssh_probe,
    parse_volume,
)
from .websocket import (
    MisterIndexStatus,
    MisterWebSocketClient,
    apply_ws_message,
    parse_index_status,
    split_menu_navigation,
)

__all__ = [
    "BACKGROUND_MODES",
    "CMD_FIFO",
    "DEFAULT_GAMEPAD_PATH",
    "DEFAULT_GAMEPAD_PORT",
    "DEFAULT_PORT",
    "DEFAULT_SSH_PORT",
    "DEFAULT_SSH_USERNAME",
    "GAMEPAD_ACTIONS",
    "GAMEPAD_BUTTONS",
    "INI_VIDEO_KEYS",
    "KEYBOARD_NAMES",
    "MDNS_SERVICE_TYPE",
    "RA_STATUS_CMD",
    "RA_SUPPORTED_SYSTEMS",
    "RA_USERNAME_PLACEHOLDER",
    "SSH_PROBE_CMD",
    "WS_PATH",
    "MisterClient",
    "MisterConnectionError",
    "MisterGamepad",
    "MisterGamepadError",
    "MisterIndexStatus",
    "MisterMainUnresponsiveError",
    "MisterRA",
    "MisterRAError",
    "MisterRAStatus",
    "MisterRAWeb",
    "MisterRAWebError",
    "MisterRAWebStats",
    "MisterSSH",
    "MisterStatus",
    "MisterUnsupportedError",
    "MisterWebSocketClient",
    "RAAchievement",
    "RAGameProgress",
    "apply_ws_message",
    "parse_game_id",
    "parse_index_status",
    "parse_ra_log",
    "parse_ra_status",
    "parse_ssh_probe",
    "parse_volume",
    "split_menu_navigation",
]
try:
    __version__ = metadata.version("python-mister-fpga")
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
