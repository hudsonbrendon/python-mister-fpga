# Changelog

## 0.3.2
- WebSocket reducer: a launch from the menu emits `gameRunning` before `coreRunning`; the core update no longer wipes that game. Only a switch from another core clears the stale game/system.

## 0.3.1
- Import `asyncssh` at module load. The lazy import inside `MisterSSH._ensure` ran on the event loop and made Home Assistant report blocking calls (liboqs/fido2 file reads) on the first SSH connection.

## 0.3.0

Findings from reverse-engineering mrext Remote 0.4/0.5 and odelot's Main_MiSTer on a real device.

**Fixes**
- `async_search_games` sent `data`; the server reads `query`, so every search returned the whole index. Adds `page` (Remote 0.5 paginates). Response is `{data, total, pageSize, page}`.
- `async_set_background_mode` used `/settings/core/menu` (answered by the web UI); the route is `/settings/cores/menu`, and only modes 0, 2, 4 … 14 are valid (`BACKGROUND_MODES`). Invalid modes now raise `ValueError`.
- `async_launch_token` now base64url-encodes the token as `/l/` requires; pass plain text such as `**random:snes`.
- Unknown routes (Remote answers them with `200 text/html`) raise `MisterUnsupportedError` instead of "invalid JSON".
- `async_get_screenshots` returns `[]` when the server sends `null`.
- Path segments (screenshots, wallpapers, scripts, playlists) are URL-quoted.
- `MisterStatus` disk fields come from the `/media/fat` entry, not just the first disk.
- WebSocket reducer: `menuNavigation:FULL:CURRENT` is split and joined into one path; arcade `gameRunning:<core>` keeps the name; a new `coreRunning` clears the stale system/game.
- Docstrings: `game` is `<system>/<file>`, not a path; `dns` is the mDNS name; raw keyboard codes are Linux evdev codes.

**New**
- Main health over SSH: `parse_ssh_probe` adds `cmd_fifo_pending` (bytes Main has not read from `/dev/MiSTer_cmd` — non-zero on two probes means Main is hung), `main_open_fds`, `volume`/`muted`, `game_id`, `sam_active`, `sam_game`.
- `MisterSSH.async_send_command` writes the command FIFO non-blocking and raises `MisterMainUnresponsiveError` instead of hanging; `async_set_volume`, `async_set_mute`.
- `MisterGamepad`: virtual controller/keyboard through the MiSTer Companion Remote daemon (port 9191).
- `parse_ra_log` / `MisterRA.async_read_log` / `MisterRA.async_set_debug`: RetroAchievements login, game identified, achievement, leaderboard, game-completed events from odelot's debug log.
- `parse_index_status` / `MisterIndexStatus` (index progress), `split_menu_navigation`, `MisterWebSocketClient.async_send` (e.g. `kbdRawDown:`/`kbdRawUp:`).
- REST: `async_delete_screenshot`, `async_get_search_systems`, `async_browse_games`, `async_browse_menu` (rejects `..`), `async_get_remote_log`, and for Remote 0.5 `async_get_screen`, `async_get_playlog_status/summary/games/sessions`; `MisterStatus.core_session_time`/`game_session_time`, `disks`.
- `MDNS_SERVICE_TYPE` for zeroconf discovery.

## 0.2.0
- Add `MisterRAWeb` — async client for the [RetroAchievements.org Web API](https://api.docs.retroachievements.org/) to pull cloud player stats (points, rank, recently-played games, latest unlocked achievement) without SSH.
- New dataclasses `MisterRAWebStats`, `RAGameProgress`, `RAAchievement` for aggregated cloud-stats snapshots.
- New exception `MisterRAWebError` raised on network, HTTP, or API-level failures (including bad credentials).

## 0.1.2
- Add online documentation (MkDocs Material) at https://hudsonbrendon.github.io/python-mister-fpga/ and enrich public-API docstrings.

## 0.1.1
- Export `DEFAULT_SSH_PORT`, `DEFAULT_SSH_USERNAME` and `SSH_PROBE_CMD` from the top-level package so consumers can reuse them without duplicating.

## 0.1.0
- Initial release: async REST client (`MisterClient`/`MisterStatus`/`MisterConnectionError`), WebSocket reducer + client (`apply_ws_message`/`MisterWebSocketClient`), and SSH telemetry (`parse_ssh_probe`/`MisterSSH`) for the MiSTer FPGA mrext Remote API.
