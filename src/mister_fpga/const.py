"""Protocol constants for the MiSTer FPGA mrext Remote API."""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PORT = 8182
HTTP_TIMEOUT = 10

# mrext Remote API paths (relative to base_url = http://host:port/api)
PATH_PLAYING = "/games/playing"
PATH_SYSINFO = "/sysinfo"
PATH_SYSTEMS = "/systems"
PATH_GAMES_LAUNCH = "/games/launch"
PATH_GAMES_SEARCH = "/games/search"
PATH_GAMES_INDEX = "/games/index"
PATH_LAUNCH_MENU = "/launch/menu"
PATH_KEYBOARD = "/controls/keyboard"
PATH_REBOOT = "/settings/system/reboot"
PATH_RESTART_REMOTE = "/settings/remote/restart"
PATH_SCREENSHOTS = "/screenshots"
PATH_MUSIC_STATUS = "/music/status"
PATH_MUSIC_PLAY = "/music/play"
PATH_MUSIC_STOP = "/music/stop"
PATH_MUSIC_NEXT = "/music/next"
PATH_MUSIC_PLAYLIST = "/music/playlist"
PATH_MUSIC_PLAYBACK = "/music/playback"
PATH_WALLPAPERS = "/wallpapers"
PATH_INIS = "/settings/inis"
PATH_CORE_MENU = "/settings/core/menu"
PATH_SCRIPTS_LIST = "/scripts/list"
PATH_SCRIPTS_LAUNCH = "/scripts/launch"
PATH_SCRIPTS_CONSOLE = "/scripts/console"
PATH_SCRIPTS_KILL = "/scripts/kill"
PATH_PEERS = "/settings/remote/peers"
PATH_LAUNCH = "/launch"
PATH_LAUNCH_TOKEN = "/l"
PATH_LAUNCH_NEW = "/launch/new"
PATH_KEYBOARD_RAW = "/controls/keyboard-raw"

# WebSocket endpoint (mounted under /api on Remote v0.4)
WS_PATH = "/api/ws"

# MiSTer.ini keys exposed as Number entities (value range 0-100)
INI_VIDEO_KEYS = ("video_brightness", "video_contrast", "video_saturation")

# SSH defaults and probe command
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USERNAME = "root"

SSH_PROBE_CMD = (
    "cat /tmp/CORENAME 2>/dev/null; echo '|||'; "
    "cat /proc/uptime 2>/dev/null; echo '|||'; "
    "cat /proc/loadavg 2>/dev/null; echo '|||'; "
    "awk '/MemTotal|MemAvailable/{print $2}' /proc/meminfo 2>/dev/null; echo '|||'; "
    "stat -c %Y /media/fat/MiSTer 2>/dev/null"
)

# Keyboard control names accepted by POST /controls/keyboard/{name}
KEYBOARD_NAMES = (
    "up", "down", "left", "right", "confirm", "back", "cancel", "menu",
    "osd", "core_select", "user", "volume_up", "volume_down", "volume_mute",
    "reset", "screenshot", "raw_screenshot", "console", "exit_console",
    "computer_osd", "change_background", "pair_bluetooth", "toggle_core_dates",
)

# RetroAchievements (local, via SSH helper scripts) ------------------------

# mrext system keys for cores with odelot RA-modified builds.
RA_SUPPORTED_SYSTEMS = (
    "NES", "FDS", "SNES", "MegaDrive", "SMS", "Gameboy", "N64", "PSX",
    "GBA", "MegaCD", "NeoGeo", "TurboGrafx16", "Atari2600", "Atari7800", "S32X",
)

# Placeholder written by the RA installer before the user fills credentials.
RA_USERNAME_PLACEHOLDER = "YOUR_RA_USERNAME"

# One-shot SSH command emitting parseable RA state. Combines an install probe,
# the username from the cfg, and ra_status.sh output.
RA_STATUS_CMD = (
    "if [ -d /media/fat/_RA_Cores ]; then echo installed=1; "
    "else echo installed=0; fi; "
    "echo \"username=$(sed -n 's/^username=//p' "
    "/media/fat/retroachievements.cfg 2>/dev/null | head -1)\"; "
    "bash /media/fat/Scripts/.ra/ra_status.sh 2>/dev/null"
)


@dataclass
class MisterRAStatus:
    """Parsed RetroAchievements local state."""

    installed: bool = False
    cores_on: bool = False
    binary_ra: bool = False
    hardcore: bool = False
    username: str | None = None
    cores_active: int = 0
    cores_total: int = 0


# RetroAchievements Web API (cloud player stats) ------------------------------

RA_WEB_API_BASE = "https://retroachievements.org/API/"
RA_WEB_IMAGE_BASE = "https://media.retroachievements.org"
RA_WEB_DEFAULT_RECENT_COUNT = 10
RA_WEB_DEFAULT_ACHIEVEMENT_MINUTES = 10080  # 7 days, in minutes


@dataclass
class RAGameProgress:
    """Per-game achievement progress from the RA Web API."""

    game_id: int
    title: str
    console: str
    num_achieved: int = 0
    num_possible: int = 0
    percent: float = 0.0
    last_played: str | None = None
    icon_url: str | None = None


@dataclass
class RAAchievement:
    """A single unlocked achievement from the RA Web API."""

    title: str
    description: str
    points: int
    game_title: str
    date: str | None = None
    badge_url: str | None = None


@dataclass
class MisterRAWebStats:
    """Aggregated RetroAchievements cloud player stats."""

    hardcore_points: int = 0
    softcore_points: int = 0
    rank: int | None = None
    total_ranked: int | None = None
    current_game: RAGameProgress | None = None
    recent_games: list[RAGameProgress] = field(default_factory=list)
    last_achievement: RAAchievement | None = None
