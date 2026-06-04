# Changelog

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
