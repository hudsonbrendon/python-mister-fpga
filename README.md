<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/dark_logo.png" width="420">
    <img src="assets/logo.png" alt="python-mister-fpga" width="420">
  </picture>
</p>

# python-mister-fpga

[![Tests](https://github.com/hudsonbrendon/python-mister-fpga/actions/workflows/tests.yml/badge.svg)](https://github.com/hudsonbrendon/python-mister-fpga/actions/workflows/tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/python-mister-fpga)](https://pypi.org/project/python-mister-fpga/)
[![Python versions](https://img.shields.io/pypi/pyversions/python-mister-fpga)](https://pypi.org/project/python-mister-fpga/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue)](https://hudsonbrendon.github.io/python-mister-fpga/)

Async Python client for the [mrext Remote API](https://github.com/wizzomafizzo/mrext) (REST + WebSocket) and optional SSH telemetry for the MiSTer FPGA. Zero Home Assistant dependency — use it in any Python project.

## Install

```bash
pip install python-mister-fpga
```

## Usage

### REST client

```python
import asyncio
from mister_fpga import MisterClient

async def main():
    client = MisterClient("192.168.1.50")
    status = await client.async_get_status()
    print(status.core, status.game)
    await client.async_launch_game("/media/fat/games/SNES/Chrono.sfc")
    await client.async_close()

asyncio.run(main())
```

### WebSocket (real-time updates)

```python
import asyncio
from mister_fpga import MisterWebSocketClient, MisterStatus, apply_ws_message

state = MisterStatus(online=True)
menu_path = None
index_state = (False, False)

def on_message(text: str) -> None:
    global state, menu_path, index_state
    state, menu_path, index_state = apply_ws_message(text, state, menu_path, index_state)
    print(state.core, state.game)

async def main():
    ws = MisterWebSocketClient("192.168.1.50")
    await ws.listen(on_message)

asyncio.run(main())
```

### SSH telemetry

```python
import asyncio
from mister_fpga import MisterSSH

async def main():
    ssh = MisterSSH("192.168.1.50", 22, "root", "1")
    data = await ssh.async_probe()
    print(data)
    await ssh.async_close()

asyncio.run(main())
```

## RetroAchievements cloud stats

`MisterRAWeb` queries the public [RetroAchievements.org Web API](https://api.docs.retroachievements.org/) to pull a player's points, rank, recently-played games, and latest unlocked achievement — no SSH required.  You need a **Web API key** from [retroachievements.org/settings](https://retroachievements.org/settings).

```python
from mister_fpga import MisterRAWeb

web = MisterRAWeb("myuser", "my_api_key")
stats = await web.async_fetch_stats()
print(stats.hardcore_points, stats.rank, stats.current_game)
await web.async_close()
```

### `MisterRAWeb(username, api_key, *, session=None, timeout=15)`

Async HTTPS client for the RA Web API.  When `session` is `None` the client creates its own `aiohttp.ClientSession`; call `await web.async_close()` to release it.  Pass a shared session to manage its lifetime yourself.

| Method | Description |
|---|---|
| `await async_fetch_stats() -> MisterRAWebStats` | Fire all three API calls concurrently and return an aggregated stats snapshot. |
| `await async_validate()` | Lightweight credential check — raises `MisterRAWebError` if the username or API key is wrong. |
| `await async_get_badge_image(url) -> bytes` | Fetch a badge or icon image by absolute URL (e.g. `stats.last_achievement.badge_url`). |
| `await async_close()` | Close the session if this client created it. |

### Dataclasses

**`MisterRAWebStats`** — aggregated snapshot returned by `async_fetch_stats()`:

| Field | Type | Description |
|---|---|---|
| `hardcore_points` | `int` | Total hardcore score. |
| `softcore_points` | `int` | Total softcore score. |
| `rank` | `int \| None` | Global hardcore rank (None if unranked). |
| `total_ranked` | `int \| None` | Total number of ranked players. |
| `current_game` | `RAGameProgress \| None` | Most recently played game (first entry in the recent-games list). |
| `recent_games` | `list[RAGameProgress]` | Up to 10 recently played games, most-recent first. |
| `last_achievement` | `RAAchievement \| None` | Most recently unlocked achievement (within the last 7 days). |

**`RAGameProgress`** — per-game achievement progress:

| Field | Type | Description |
|---|---|---|
| `game_id` | `int` | RA game ID. |
| `title` | `str` | Game title. |
| `console` | `str` | Console name (e.g. `"SNES"`). |
| `num_achieved` | `int` | Achievements unlocked by the player. |
| `num_possible` | `int` | Total achievements in the set. |
| `percent` | `float` | Completion percentage (0–100). |
| `last_played` | `str \| None` | ISO-ish timestamp of last session. |
| `icon_url` | `str \| None` | Absolute URL of the game icon. |

**`RAAchievement`** — a single unlocked achievement:

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Achievement title. |
| `description` | `str` | Achievement description. |
| `points` | `int` | Point value. |
| `game_title` | `str` | Title of the game it belongs to. |
| `date` | `str \| None` | Unlock timestamp. |
| `badge_url` | `str \| None` | Absolute URL of the badge image. |

**`MisterRAWebError`** — raised by `MisterRAWeb` on network failures, HTTP errors, or API-level errors (including bad credentials).

## API

- **`MisterClient(host, port=8182, *, session=None, timeout=10)`** — async REST client; call `await client.async_close()` when done, or inject your own `aiohttp.ClientSession`.
- **`MisterStatus`** — dataclass snapshot: `online`, `core`, `system`, `game`, `hostname`, `version`, `ip`, `ips`, `dns`, `disk_total/used/free`. Property `is_running_game`.
- **`MisterConnectionError`** — raised on network/HTTP errors.
- **`MisterWebSocketClient(host, port=8182, *, session=None, reconnect_delay=5)`** — reconnecting WS loop; `await ws.listen(callback)`, call `ws.stop()` to exit.
- **`apply_ws_message(message, status, menu_path, index_state)`** — pure reducer; apply a single WS text frame and return updated `(status, menu_path, index_state)`.
- **`MisterSSH(host, port, username, password)`** — persistent asyncssh connection; `await ssh.async_probe()` returns telemetry dict.
- **`parse_ssh_probe(raw)`** — parse the raw batched SSH output into a telemetry dict.
- **`MisterRAWeb(username, api_key, *, session=None, timeout=15)`** — async RA Web API client; `await web.async_fetch_stats()` returns `MisterRAWebStats`.
- **`MisterRAWebStats`**, **`RAGameProgress`**, **`RAAchievement`** — cloud-stats dataclasses (see section above).
- **`MisterRAWebError`** — raised on RA Web API failures.
- **`KEYBOARD_NAMES`**, **`INI_VIDEO_KEYS`**, **`WS_PATH`**, **`DEFAULT_PORT`** — protocol constants.

## Documentation

Full documentation is available at **https://hudsonbrendon.github.io/python-mister-fpga/** — usage guide, runnable examples, and auto-generated API reference.

## Credits

REST/WebSocket API by [wizzomafizzo/mrext](https://github.com/wizzomafizzo/mrext). MiSTer-kun logo by the MiSTer-devel project. Author [@hudsonbrendon](https://github.com/hudsonbrendon).

## License

MIT — see [LICENSE](LICENSE).
