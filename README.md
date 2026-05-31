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

## API

- **`MisterClient(host, port=8182, *, session=None, timeout=10)`** — async REST client; call `await client.async_close()` when done, or inject your own `aiohttp.ClientSession`.
- **`MisterStatus`** — dataclass snapshot: `online`, `core`, `system`, `game`, `hostname`, `version`, `ip`, `ips`, `dns`, `disk_total/used/free`. Property `is_running_game`.
- **`MisterConnectionError`** — raised on network/HTTP errors.
- **`MisterWebSocketClient(host, port=8182, *, session=None, reconnect_delay=5)`** — reconnecting WS loop; `await ws.listen(callback)`, call `ws.stop()` to exit.
- **`apply_ws_message(message, status, menu_path, index_state)`** — pure reducer; apply a single WS text frame and return updated `(status, menu_path, index_state)`.
- **`MisterSSH(host, port, username, password)`** — persistent asyncssh connection; `await ssh.async_probe()` returns telemetry dict.
- **`parse_ssh_probe(raw)`** — parse the raw batched SSH output into a telemetry dict.
- **`KEYBOARD_NAMES`**, **`INI_VIDEO_KEYS`**, **`WS_PATH`**, **`DEFAULT_PORT`** — protocol constants.

## Documentation

Full documentation is available at **https://hudsonbrendon.github.io/python-mister-fpga/** — usage guide, runnable examples, and auto-generated API reference.

## Credits

REST/WebSocket API by [wizzomafizzo/mrext](https://github.com/wizzomafizzo/mrext). MiSTer-kun logo by the MiSTer-devel project. Author [@hudsonbrendon](https://github.com/hudsonbrendon).

## License

MIT — see [LICENSE](LICENSE).
