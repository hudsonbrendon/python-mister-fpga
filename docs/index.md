<p align="center"><img src="assets/logo.png" width="380" alt="python-mister-fpga"></p>

# python-mister-fpga

**python-mister-fpga** is an async Python library for controlling and monitoring a
[MiSTer FPGA](https://github.com/MiSTer-devel/Main_MiSTer/wiki) device through the
[mrext Remote API](https://github.com/wizzomafizzo/mrext).  It covers the full
REST surface (launch cores/games, screenshots, music, wallpapers, INI files,
scripts, and more), a reconnecting WebSocket client for real-time state updates,
and optional SSH telemetry — all with no Home Assistant dependency.

## Install

```bash
pip install python-mister-fpga
```

## Quickstart

```python
import asyncio
from mister_fpga import MisterClient

async def main():
    client = MisterClient("192.168.1.50")
    status = await client.async_get_status()
    print(status.core, status.game)
    await client.async_close()

asyncio.run(main())
```

## Next steps

- [Usage guide](usage.md) — full runnable examples for REST, WebSocket, and SSH.
- [API reference](api.md) — auto-generated from docstrings.
- [Changelog](changelog.md) — version history.
