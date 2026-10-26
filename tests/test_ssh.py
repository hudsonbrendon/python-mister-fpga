"""Tests for the optional SSH telemetry parsing."""
from __future__ import annotations

import pytest

from mister_fpga.ssh import MisterSSH, parse_ssh_probe


def test_parse_ssh_probe_full():
    raw = (
        "SNES\n|||\n123456.78 100.0\n|||\n0.50 0.40 0.30 1/98 1234"
        "\n|||\n1048576\n524288\n|||\n1742860800"
    )
    data = parse_ssh_probe(raw)
    assert data["active_core"] == "SNES"
    assert data["uptime_seconds"] == 123456
    assert data["cpu_load_1m"] == 0.50
    assert data["memory_used_percent"] == 50.0
    assert data["firmware_timestamp"] == 1742860800


def test_parse_ssh_probe_partial_is_tolerant():
    raw = "MENU\n|||\n\n|||\n\n|||\n\n|||\n"
    data = parse_ssh_probe(raw)
    assert data["active_core"] == "MENU"
    assert data["uptime_seconds"] is None
    assert data["memory_used_percent"] is None


class _FakeResult:
    def __init__(self, stdout="", exit_status=0):
        self.stdout = stdout
        self.exit_status = exit_status


class _FakeConn:
    def __init__(self, result):
        self._result = result
        self.commands = []

    async def run(self, command, check=False, timeout=10):
        self.commands.append(command)
        return self._result

    def close(self):
        pass


@pytest.mark.asyncio
async def test_async_run_returns_rc_and_stdout(monkeypatch):
    ssh = MisterSSH("h", 22, "root", "1")
    ssh._conn = _FakeConn(_FakeResult(stdout="hello", exit_status=0))
    rc, out = await ssh.async_run("echo hello")
    assert rc == 0
    assert out == "hello"
    assert ssh._conn.commands == ["echo hello"]


@pytest.mark.asyncio
async def test_async_run_propagates_nonzero(monkeypatch):
    ssh = MisterSSH("h", 22, "root", "1")
    ssh._conn = _FakeConn(_FakeResult(stdout="boom", exit_status=3))
    rc, out = await ssh.async_run("false")
    assert rc == 3
    assert out == "boom"


@pytest.mark.asyncio
async def test_async_run_raises_and_drops_conn_on_error():
    ssh = MisterSSH("h", 22, "root", "1")

    class _BoomConn:
        async def run(self, *a, **k):
            raise OSError("down")

        def close(self):
            pass

    ssh._conn = _BoomConn()
    with pytest.raises(OSError):
        await ssh.async_run("x")
    assert ssh._conn is None


def test_parse_ssh_probe_health_fields():
    raw = (
        "PSX|||\n368.96 234.28\n|||\n1.79 1.68 0.83 2/118 3778\n|||\n504096\n384160"
        "\n|||\n1785466274\n|||\n65229\n|||\n131\n|||\n  16\n|||\n"
        "Serial: SLUS-00668\n|||\n1\n|||\nParasite Eve (US) (psx)"
    )
    data = parse_ssh_probe(raw)
    assert data["cmd_fifo_pending"] == 65229
    assert data["main_open_fds"] == 131
    assert data["volume"] == 7 and data["muted"] is True
    assert data["game_id"] == "SLUS-00668"
    assert data["sam_active"] is True
    assert data["sam_game"] == "Parasite Eve (US) (psx)"


def test_parse_volume():
    from mister_fpga import parse_volume

    assert parse_volume(0) == (7, False)
    assert parse_volume(7) == (0, False)
    assert parse_volume(0x13) == (4, True)
    assert parse_volume(None) == (None, None)


@pytest.mark.asyncio
async def test_send_command_quotes_and_detects_hang():
    from mister_fpga import MisterMainUnresponsiveError

    ssh = MisterSSH("h", 22, "root", "1")
    ssh._conn = _FakeConn(_FakeResult(stdout="", exit_status=0))
    await ssh.async_send_command("load_core /media/fat/games/x y'z.mgl")
    expected = """'load_core /media/fat/games/x y'"'"'z.mgl'"""
    assert ssh._conn.commands[0].endswith(expected)

    ssh._conn = _FakeConn(_FakeResult(stdout="[Errno 11] EAGAIN", exit_status=3))
    with pytest.raises(MisterMainUnresponsiveError):
        await ssh.async_set_volume(5)
    with pytest.raises(ValueError):
        await ssh.async_send_command("volume 1\nvolume 2")
