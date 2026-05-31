# Usage

## REST client

Use `MisterClient` to call the mrext Remote REST API.  All methods are `async`;
call `async_close()` when done (or inject your own `aiohttp.ClientSession` and
manage its lifetime yourself).

```python
import asyncio
from mister_fpga import MisterClient

async def main():
    client = MisterClient("192.168.1.50")
    try:
        # Fetch combined sysinfo + playing snapshot
        status = await client.async_get_status()
        print("Core :", status.core)
        print("Game :", status.game_name)
        print("Online:", status.online)

        # Launch a game by its absolute SD-card path
        await client.async_launch_game("/media/fat/games/SNES/Chrono Trigger.sfc")

        # Search the game index
        results = await client.async_search_games("Chrono", system="snes")
        print(results)

        # Return to the main menu
        await client.async_launch_menu()
    finally:
        await client.async_close()

asyncio.run(main())
```

## WebSocket (real-time updates)

`MisterWebSocketClient` connects to the mrext WebSocket endpoint and calls your
callback for every TEXT frame.  Pair it with `apply_ws_message` — a pure
reducer — to keep a local `MisterStatus` in sync without polling.

```python
import asyncio
from mister_fpga import MisterWebSocketClient, MisterStatus, apply_ws_message

state = MisterStatus(online=True)
menu_path = None
index_state = (False, False)

def on_message(text: str) -> None:
    global state, menu_path, index_state
    state, menu_path, index_state = apply_ws_message(
        text, state, menu_path, index_state
    )
    print(f"core={state.core}  game={state.game_name}")

async def main():
    ws = MisterWebSocketClient("192.168.1.50")
    # listen() blocks and reconnects automatically; cancel the task to stop.
    await ws.listen(on_message)

asyncio.run(main())
```

To stop the loop from outside (e.g. on a signal), call `ws.stop()`.

## SSH telemetry

`MisterSSH` opens a persistent asyncssh connection and runs a batched probe
command that collects active core, uptime, CPU load, memory usage, and firmware
timestamp in a single round-trip.  The probe is best-effort: it returns `{}`
instead of raising on any SSH failure.

```python
import asyncio
from mister_fpga import MisterSSH

async def main():
    ssh = MisterSSH("192.168.1.50", port=22, username="root", password="1")
    try:
        data = await ssh.async_probe()
        print("Active core      :", data.get("active_core"))
        print("Uptime (seconds) :", data.get("uptime_seconds"))
        print("CPU load (1m)    :", data.get("cpu_load_1m"))
        print("Memory used %    :", data.get("memory_used_percent"))
        print("Firmware mtime   :", data.get("firmware_timestamp"))
    finally:
        await ssh.async_close()

asyncio.run(main())
```
