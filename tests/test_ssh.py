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
