"""Tests for the device_manager module."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import Settings
from device_manager import Device, DeviceLocation, _nova_request, _parse_location_report, list_devices, ring_device
from proto import Common_pb2, DeviceUpdate_pb2


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Create test settings with a temporary secrets directory."""
    return Settings(secrets_dir=tmp_path)


def test_device_location_google_maps_url() -> None:
    """Test Google Maps URL generation."""
    loc = DeviceLocation(
        latitude=48.8566,
        longitude=2.3522,
        accuracy=10.0,
        timestamp=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        status="LAST_KNOWN",
        location_name="Paris",
    )
    assert "48.8566" in loc.google_maps_url
    assert "2.3522" in loc.google_maps_url
    assert loc.google_maps_url.startswith("https://www.google.com/maps")


def test_device_creation() -> None:
    """Test Device dataclass creation."""
    device = Device(
        name="Pixel 9",
        canonic_id="abc123",
        device_type="Android",
        manufacturer="Google",
        model="Pixel 9",
        locations=[],
    )
    assert device.name == "Pixel 9"
    assert device.canonic_id == "abc123"
    assert device.device_type == "Android"


def test_device_is_immutable() -> None:
    """Test that Device is frozen."""
    device = Device(
        name="Test",
        canonic_id="id",
        device_type="Android",
        manufacturer="",
        model="",
    )
    with pytest.raises(AttributeError):
        device.name = "Changed"  # type: ignore[misc]


def test_device_location_is_immutable() -> None:
    """Test that DeviceLocation is frozen."""
    loc = DeviceLocation(
        latitude=0.0,
        longitude=0.0,
        accuracy=0.0,
        timestamp=None,
        status="UNKNOWN",
        location_name="",
    )
    with pytest.raises(AttributeError):
        loc.latitude = 1.0  # type: ignore[misc]


def _build_device_list_response() -> bytes:
    """Build a fake DevicesList protobuf response."""
    response = DeviceUpdate_pb2.DevicesList()

    device = response.deviceMetadata.add()
    device.userDefinedDeviceName = "Pixel 9"
    device.identifierInformation.type = DeviceUpdate_pb2.IDENTIFIER_ANDROID
    phone_id = device.identifierInformation.phoneInformation.canonicIds.canonicId.add()
    phone_id.id = "canonic-123"
    device.information.deviceRegistration.manufacturer = "Google"
    device.information.deviceRegistration.model = "Pixel 9"

    return response.SerializeToString()


def test_list_devices(settings: Settings) -> None:
    """Test listing devices with mocked API."""
    fake_response = _build_device_list_response()

    with patch("device_manager._nova_request", return_value=fake_response):
        devices = list_devices(settings)

    assert len(devices) == 1
    assert devices[0].name == "Pixel 9"
    assert devices[0].canonic_id == "canonic-123"
    assert devices[0].device_type == "Android"
    assert devices[0].manufacturer == "Google"


def test_list_devices_empty(settings: Settings) -> None:
    """Test listing devices when none are available."""
    empty_response = DeviceUpdate_pb2.DevicesList().SerializeToString()

    with patch("device_manager._nova_request", return_value=empty_response):
        devices = list_devices(settings)

    assert len(devices) == 0


def test_ring_device_success(settings: Settings) -> None:
    """Test ringing a device successfully."""
    with patch("device_manager._nova_request", return_value=b""):
        result = ring_device(settings, "canonic-123")
    assert result is True


def test_ring_device_stop(settings: Settings) -> None:
    """Test stopping ring on a device."""
    with patch("device_manager._nova_request", return_value=b""):
        result = ring_device(settings, "canonic-123", stop=True)
    assert result is True


def test_ring_device_failure(settings: Settings) -> None:
    """Test ring failure handling."""
    with patch("device_manager._nova_request", side_effect=RuntimeError("API error")):
        result = ring_device(settings, "canonic-123")
    assert result is False


def test_nova_request_success(settings: Settings) -> None:
    """Test _nova_request makes HTTP call correctly."""
    with (
        patch("device_manager.get_adm_token", return_value="test_token"),
        patch("device_manager.httpx.Client") as mock_client_cls,
    ):
        mock_response = mock_client_cls.return_value.__enter__.return_value.post.return_value
        mock_response.status_code = 200
        mock_response.content = b"response_data"

        result = _nova_request(settings, "nbe_list_devices", b"payload")
        assert result == b"response_data"


def test_nova_request_failure(settings: Settings) -> None:
    """Test _nova_request raises on HTTP error."""
    with (
        patch("device_manager.get_adm_token", return_value="test_token"),
        patch("device_manager.refresh_access_token", return_value="refreshed_token"),
        patch("device_manager.httpx.Client") as mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_response_401 = MagicMock(status_code=401, text="Unauthorized")
        mock_response_500 = MagicMock(status_code=500, text="Server Error")
        mock_client.post.side_effect = [mock_response_401, mock_response_500]

        with pytest.raises(RuntimeError, match="500"):
            _nova_request(settings, "nbe_list_devices", b"payload")


def test_parse_location_report_semantic() -> None:
    """Test parsing a semantic location report."""
    report = Common_pb2.LocationReport()
    report.semanticLocation.locationName = "Home"
    report.status = Common_pb2.SEMANTIC

    ts = Common_pb2.Time()
    ts.seconds = 1700000000

    loc = _parse_location_report(report, ts)
    assert loc is not None
    assert loc.location_name == "Home"
    assert loc.status == "SEMANTIC"
    assert loc.timestamp is not None


def test_parse_location_report_no_data() -> None:
    """Test parsing an empty location report returns None."""
    report = Common_pb2.LocationReport()
    loc = _parse_location_report(report)
    assert loc is None


def test_parse_location_report_encrypted() -> None:
    """Test parsing encrypted location report returns None."""
    report = Common_pb2.LocationReport()
    report.geoLocation.encryptedReport.encryptedLocation = b"encrypted_data"
    report.geoLocation.encryptedReport.isOwnReport = True

    loc = _parse_location_report(report)
    assert loc is None


def test_list_devices_with_location(settings: Settings) -> None:
    """Test listing devices that have semantic location data."""
    response = DeviceUpdate_pb2.DevicesList()
    device = response.deviceMetadata.add()
    device.userDefinedDeviceName = "My Phone"
    device.identifierInformation.type = DeviceUpdate_pb2.IDENTIFIER_ANDROID
    phone_id = device.identifierInformation.phoneInformation.canonicIds.canonicId.add()
    phone_id.id = "loc-device-1"

    recent = device.information.locationInformation.reports.recentLocationAndNetworkLocations
    recent.recentLocation.semanticLocation.locationName = "Office"
    recent.recentLocation.status = 0
    recent.recentLocationTimestamp.seconds = 1700000000

    with patch("device_manager._nova_request", return_value=response.SerializeToString()):
        devices = list_devices(settings)

    assert len(devices) == 1
    assert devices[0].locations[0].location_name == "Office"


def test_list_devices_spot_type(settings: Settings) -> None:
    """Test listing spot/tracker devices."""
    response = DeviceUpdate_pb2.DevicesList()
    device = response.deviceMetadata.add()
    device.userDefinedDeviceName = "My Tracker"
    device.identifierInformation.type = DeviceUpdate_pb2.IDENTIFIER_SPOT
    tracker_id = device.identifierInformation.canonicIds.canonicId.add()
    tracker_id.id = "tracker-1"

    with patch("device_manager._nova_request", return_value=response.SerializeToString()):
        devices = list_devices(settings)

    assert len(devices) == 1
    assert devices[0].device_type == "Tracker"
    assert devices[0].canonic_id == "tracker-1"
