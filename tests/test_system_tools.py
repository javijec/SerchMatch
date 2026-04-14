"""Tests for external tool helpers."""

from __future__ import annotations

from services.system_tools import get_command_status


def test_get_command_status_detects_python() -> None:
    """Python executable should be discoverable in test environment."""
    status = get_command_status("python", ["--version"])
    assert status.path is not None
