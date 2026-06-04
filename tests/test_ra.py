"""Tests for the RetroAchievements local module."""
from mister_fpga.const import RA_SUPPORTED_SYSTEMS, MisterRAStatus


def test_ra_status_defaults():
    status = MisterRAStatus()
    assert status.installed is False
    assert status.cores_on is False
    assert status.binary_ra is False
    assert status.hardcore is False
    assert status.username is None
    assert status.cores_active == 0
    assert status.cores_total == 0


def test_supported_systems_contains_core_keys():
    assert "NES" in RA_SUPPORTED_SYSTEMS
    assert "SNES" in RA_SUPPORTED_SYSTEMS
    assert "PSX" in RA_SUPPORTED_SYSTEMS


from mister_fpga.ra import parse_ra_status

_STATUS_ON = """installed=1
username=hudsonbrendon
ra_status v0.4.0
Mode flag: ON
Hardcore : OFF
/media/fat/MiSTer : RA (odelot)

CORE         STATE   DETAILS
----         -----   -------
NES          RA      -> NES.rbf (1 symlink(s), 1 stashed)
SNES         RA      -> SNES.rbf (1 symlink(s), 1 stashed)
PSX          STOCK   PSX_20260411.rbf
"""

_STATUS_OFF = """installed=1
username=YOUR_RA_USERNAME
Mode flag: never toggled
Hardcore : OFF
/media/fat/MiSTer : STOCK
NES          STOCK   NES_20260603.rbf
"""

_NOT_INSTALLED = "installed=0\nusername=\n"


def test_parse_status_on():
    s = parse_ra_status(_STATUS_ON)
    assert s.installed is True
    assert s.cores_on is True
    assert s.binary_ra is True
    assert s.hardcore is False
    assert s.username == "hudsonbrendon"
    assert s.cores_total == 3
    assert s.cores_active == 2


def test_parse_status_off_treats_placeholder_username_as_none():
    s = parse_ra_status(_STATUS_OFF)
    assert s.installed is True
    assert s.cores_on is False
    assert s.binary_ra is False
    assert s.username is None
    assert s.cores_total == 1
    assert s.cores_active == 0


def test_parse_not_installed():
    s = parse_ra_status(_NOT_INSTALLED)
    assert s.installed is False
    assert s.username is None
    assert s.cores_total == 0


def test_parse_hardcore_on_with_trailing_note():
    s = parse_ra_status(
        "installed=1\nMode flag: ON\n"
        "Hardcore : ON  (NES/FDS only enforced upstream)\n"
        "/media/fat/MiSTer : RA (odelot)\n"
    )
    assert s.hardcore is True


def test_parse_malformed_does_not_crash():
    s = parse_ra_status("garbage\n\nnonsense line")
    assert s.installed is False
    assert s.cores_total == 0


import pytest

from mister_fpga.ra import MisterRA, MisterRAError


class _FakeSSH:
    def __init__(self, rc=0, out=""):
        self._rc = rc
        self._out = out
        self.commands = []

    async def async_run(self, command, timeout=15):
        self.commands.append(command)
        return self._rc, self._out


class _RaisingSSH:
    async def async_run(self, command, timeout=15):
        raise OSError("ssh down")


@pytest.mark.asyncio
async def test_async_status_parses():
    ssh = _FakeSSH(out=_STATUS_ON)
    ra = MisterRA(ssh)
    status = await ra.async_status()
    assert status is not None
    assert status.cores_on is True
    assert status.username == "hudsonbrendon"


@pytest.mark.asyncio
async def test_async_status_none_on_ssh_failure():
    ra = MisterRA(_RaisingSSH())
    assert await ra.async_status() is None


@pytest.mark.asyncio
async def test_cores_on_off_commands():
    ssh = _FakeSSH()
    ra = MisterRA(ssh)
    await ra.async_cores_on()
    await ra.async_cores_off()
    assert ssh.commands == [
        "bash /media/fat/Scripts/.ra/ra_on.sh",
        "bash /media/fat/Scripts/.ra/ra_off.sh",
    ]


@pytest.mark.asyncio
async def test_set_hardcore_arg():
    ssh = _FakeSSH()
    ra = MisterRA(ssh)
    await ra.async_set_hardcore(True)
    await ra.async_set_hardcore(False)
    assert ssh.commands == [
        "bash /media/fat/Scripts/.ra/ra_hardcore.sh on",
        "bash /media/fat/Scripts/.ra/ra_hardcore.sh off",
    ]


@pytest.mark.asyncio
async def test_control_raises_on_nonzero():
    ra = MisterRA(_FakeSSH(rc=1, out="fail"))
    with pytest.raises(MisterRAError):
        await ra.async_cores_on()


def test_public_exports():
    import mister_fpga

    assert hasattr(mister_fpga, "MisterRA")
    assert hasattr(mister_fpga, "MisterRAStatus")
    assert hasattr(mister_fpga, "MisterRAError")
    assert hasattr(mister_fpga, "RA_SUPPORTED_SYSTEMS")
    assert mister_fpga.__version__ == "0.1.3"
