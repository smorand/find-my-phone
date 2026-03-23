"""Tests for protobuf message serialization/deserialization."""

import pytest

from proto import Common_pb2, DeviceUpdate_pb2


def test_devices_list_request_serialization() -> None:
    """Test that DevicesListRequest serializes and deserializes correctly."""
    request = DeviceUpdate_pb2.DevicesListRequest()
    request.deviceListRequestPayload.type = DeviceUpdate_pb2.SPOT_DEVICE
    request.deviceListRequestPayload.id = "test-uuid"

    data = request.SerializeToString()
    assert len(data) > 0

    parsed = DeviceUpdate_pb2.DevicesListRequest()
    parsed.ParseFromString(data)
    assert parsed.deviceListRequestPayload.type == DeviceUpdate_pb2.SPOT_DEVICE
    assert parsed.deviceListRequestPayload.id == "test-uuid"


def test_execute_action_request_ring() -> None:
    """Test ring action request serialization."""
    request = DeviceUpdate_pb2.ExecuteActionRequest()
    request.scope.type = DeviceUpdate_pb2.SPOT_DEVICE
    request.scope.device.canonicId.id = "device-123"
    request.requestMetadata.type = DeviceUpdate_pb2.SPOT_DEVICE
    request.requestMetadata.requestUuid = "req-uuid"
    request.requestMetadata.fmdClientUuid = "client-uuid"
    request.requestMetadata.gcmRegistrationId.id = ""
    request.requestMetadata.unknown = True
    request.action.startSound.component = DeviceUpdate_pb2.DEVICE_COMPONENT_UNSPECIFIED

    data = request.SerializeToString()
    assert len(data) > 0

    parsed = DeviceUpdate_pb2.ExecuteActionRequest()
    parsed.ParseFromString(data)
    assert parsed.scope.device.canonicId.id == "device-123"
    assert parsed.requestMetadata.requestUuid == "req-uuid"


def test_devices_list_response_parsing() -> None:
    """Test parsing a DevicesList response."""
    response = DeviceUpdate_pb2.DevicesList()

    device = response.deviceMetadata.add()
    device.userDefinedDeviceName = "My Pixel"
    device.identifierInformation.type = DeviceUpdate_pb2.IDENTIFIER_ANDROID
    phone_id = device.identifierInformation.phoneInformation.canonicIds.canonicId.add()
    phone_id.id = "canonic-id-123"

    data = response.SerializeToString()
    parsed = DeviceUpdate_pb2.DevicesList()
    parsed.ParseFromString(data)

    assert len(parsed.deviceMetadata) == 1
    assert parsed.deviceMetadata[0].userDefinedDeviceName == "My Pixel"
    assert parsed.deviceMetadata[0].identifierInformation.type == DeviceUpdate_pb2.IDENTIFIER_ANDROID


def test_location_report() -> None:
    """Test LocationReport with semantic location."""
    report = Common_pb2.LocationReport()
    report.semanticLocation.locationName = "Home"
    report.status = Common_pb2.SEMANTIC

    data = report.SerializeToString()
    parsed = Common_pb2.LocationReport()
    parsed.ParseFromString(data)

    assert parsed.semanticLocation.locationName == "Home"
    assert parsed.status == Common_pb2.SEMANTIC


def test_location_coordinates() -> None:
    """Test Location message with coordinates."""
    loc = DeviceUpdate_pb2.Location()
    loc.latitude = 488566000
    loc.longitude = 23522000
    loc.altitude = 35

    data = loc.SerializeToString()
    parsed = DeviceUpdate_pb2.Location()
    parsed.ParseFromString(data)

    assert parsed.latitude / 1e7 == pytest.approx(48.8566, abs=0.0001)
    assert parsed.longitude / 1e7 == pytest.approx(2.3522, abs=0.0001)
    assert parsed.altitude == 35
