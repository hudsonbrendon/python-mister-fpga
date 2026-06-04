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
