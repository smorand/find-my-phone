"""Tests for the find_my_phone CLI module."""

from unittest.mock import patch

from typer.testing import CliRunner

from device_manager import Device, DeviceLocation
from find_my_phone import app

runner = CliRunner()

FAKE_DEVICES = [
    Device(
        name="Pixel 9",
        canonic_id="canonic-123",
        device_type="Android",
        manufacturer="Google",
        model="Pixel 9",
        locations=[
            DeviceLocation(
                latitude=48.8566,
                longitude=2.3522,
                accuracy=10.0,
                timestamp=None,
                status="LAST_KNOWN",
                location_name="Paris",
            )
        ],
    ),
]


def test_help() -> None:
    """Test that help command works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Find My Phone" in result.output


def test_list_not_logged_in() -> None:
    """Test that list command fails when not logged in."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_ring_not_logged_in() -> None:
    """Test that ring command fails when not logged in."""
    result = runner.invoke(app, ["ring", "1"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_locate_not_logged_in() -> None:
    """Test that locate command fails when not logged in."""
    result = runner.invoke(app, ["locate", "1"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_verbose_flag() -> None:
    """Test that verbose flag is accepted."""
    result = runner.invoke(app, ["-v", "--help"])
    assert result.exit_code == 0


def test_quiet_flag() -> None:
    """Test that quiet flag is accepted."""
    result = runner.invoke(app, ["-q", "--help"])
    assert result.exit_code == 0


def test_list_devices_logged_in() -> None:
    """Test list command when logged in."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=FAKE_DEVICES),
    ):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Pixel 9" in result.output


def test_list_empty() -> None:
    """Test list command with no devices."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=[]),
    ):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No devices" in result.output


def test_ring_logged_in() -> None:
    """Test ring command by index."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=FAKE_DEVICES),
        patch("device_manager.ring_device", return_value=True),
    ):
        result = runner.invoke(app, ["ring", "1"])
    assert result.exit_code == 0
    assert "ringing" in result.output.lower()


def test_ring_stop() -> None:
    """Test ring stop command."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=FAKE_DEVICES),
        patch("device_manager.ring_device", return_value=True),
    ):
        result = runner.invoke(app, ["ring", "1", "--stop"])
    assert result.exit_code == 0
    assert "stopped" in result.output.lower()


def test_ring_failure() -> None:
    """Test ring command failure."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=FAKE_DEVICES),
        patch("device_manager.ring_device", return_value=False),
    ):
        result = runner.invoke(app, ["ring", "1"])
    assert result.exit_code == 1
    assert "Failed" in result.output


def test_locate_logged_in() -> None:
    """Test locate command."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=FAKE_DEVICES),
    ):
        result = runner.invoke(app, ["locate", "1"])
    assert result.exit_code == 0
    assert "Paris" in result.output


def test_locate_no_location() -> None:
    """Test locate command when no location data."""
    no_loc_devices = [
        Device(name="Pixel 9", canonic_id="canonic-123", device_type="Android", manufacturer="", model=""),
    ]
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=no_loc_devices),
    ):
        result = runner.invoke(app, ["locate", "1"])
    assert result.exit_code == 0
    assert "No location" in result.output


def test_locate_with_coordinates() -> None:
    """Test locate command with coordinates."""
    devices_with_coords = [
        Device(
            name="Phone",
            canonic_id="id-1",
            device_type="Android",
            manufacturer="",
            model="",
            locations=[
                DeviceLocation(
                    latitude=48.8566,
                    longitude=2.3522,
                    accuracy=15.0,
                    timestamp=None,
                    status="LAST_KNOWN",
                    location_name="",
                )
            ],
        ),
    ]
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=devices_with_coords),
    ):
        result = runner.invoke(app, ["locate", "1"])
    assert result.exit_code == 0
    assert "48.8566" in result.output
    assert "google.com/maps" in result.output


def test_resolve_device_by_canonic_id() -> None:
    """Test resolving device by canonic ID directly."""
    with (
        patch("auth.is_logged_in", return_value=True),
        patch("device_manager.list_devices", return_value=FAKE_DEVICES),
    ):
        result = runner.invoke(app, ["locate", "canonic-123"])
    assert result.exit_code == 0
    assert "Pixel 9" in result.output
