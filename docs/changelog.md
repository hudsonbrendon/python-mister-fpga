# Changelog

## 0.1.2

- Add online documentation (MkDocs Material) at <https://hudsonbrendon.github.io/python-mister-fpga/> and enrich public-API docstrings.

## 0.1.1

- Export `DEFAULT_SSH_PORT`, `DEFAULT_SSH_USERNAME` and `SSH_PROBE_CMD` from the top-level package so consumers can reuse them without duplicating.

## 0.1.0

- Initial release: async REST client (`MisterClient`/`MisterStatus`/`MisterConnectionError`), WebSocket reducer + client (`apply_ws_message`/`MisterWebSocketClient`), and SSH telemetry (`parse_ssh_probe`/`MisterSSH`) for the MiSTer FPGA mrext Remote API.
