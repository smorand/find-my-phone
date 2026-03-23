"""Device manager for Google Find My Device Nova API.

Handles listing devices, ringing, and retrieving location data
via the internal android.googleapis.com/nova/ endpoints.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from auth import get_adm_token, refresh_access_token
from proto import DeviceUpdate_pb2
from tracing import trace_span

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)

NOVA_BASE_URL = "https://android.googleapis.com/nova"
NOVA_LIST_SCOPE = "nbe_list_devices"
NOVA_ACTION_SCOPE = "nbe_execute_action"
USER_AGENT = "fmd/20006320; gzip"
HTTP_OK = 200


@dataclass(frozen=True)
class DeviceLocation:
    """Represents a device's location."""

    latitude: float
    longitude: float
    accuracy: float
    timestamp: datetime.datetime | None
    status: str
    location_name: str

    @property
    def google_maps_url(self) -> str:
        """Return a Google Maps URL for this location."""
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"


@dataclass(frozen=True)
class Device:
    """Represents a device from the Find My Device API."""

    name: str
    canonic_id: str
    device_type: str
    manufacturer: str
    model: str
    locations: list[DeviceLocation] = field(default_factory=list)


HTTP_UNAUTHORIZED = 401


def _nova_request(settings: Settings, scope: str, payload: bytes) -> bytes:
    """Send a request to the Nova API. Refreshes token on 401."""
    url = f"{NOVA_BASE_URL}/{scope}"
    adm_token = get_adm_token(settings)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Authorization": f"Bearer {adm_token}",
        "Accept-Language": "en-US",
        "User-Agent": USER_AGENT,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, content=payload)

        if response.status_code == HTTP_UNAUTHORIZED:
            logger.info("Token expired, refreshing...")
            new_token = refresh_access_token(settings)
            headers["Authorization"] = f"Bearer {new_token}"
            response = client.post(url, headers=headers, content=payload)

    if response.status_code != HTTP_OK:
        logger.error("Nova API error (HTTP %s): %s", response.status_code, response.text)
        msg = f"Nova API request failed with status {response.status_code}"
        raise RuntimeError(msg)

    return response.content


def _parse_location_report(report: Any, timestamp: Any | None = None) -> DeviceLocation | None:
    """Parse a LocationReport protobuf message into a DeviceLocation."""
    lat = 0.0
    lon = 0.0
    accuracy = 0.0
    location_name = ""
    status = "UNKNOWN"
    ts = None

    status_map = {0: "SEMANTIC", 1: "LAST_KNOWN", 2: "CROWDSOURCED", 3: "AGGREGATED"}
    status = status_map.get(report.status, f"STATUS_{report.status}")

    if report.HasField("semanticLocation") and report.semanticLocation.locationName:
        location_name = report.semanticLocation.locationName

    if report.HasField("geoLocation"):
        geo = report.geoLocation
        accuracy = geo.accuracy
        if geo.HasField("encryptedReport"):
            encrypted = geo.encryptedReport
            if encrypted.isOwnReport and encrypted.encryptedLocation:
                logger.debug("Location is encrypted (own report), cannot decode without identity key")
                return None
            if encrypted.encryptedLocation:
                logger.debug("Location is encrypted (crowdsourced), cannot decode without identity key")
                return None

    if timestamp and timestamp.seconds > 0:
        ts = datetime.datetime.fromtimestamp(timestamp.seconds, tz=datetime.UTC)

    if location_name:
        return DeviceLocation(
            latitude=lat,
            longitude=lon,
            accuracy=accuracy,
            timestamp=ts,
            status=status,
            location_name=location_name,
        )

    return None


def list_devices(settings: Settings) -> list[Device]:
    """List all devices associated with the Google account."""
    with trace_span("api.list_devices"):
        request = DeviceUpdate_pb2.DevicesListRequest()
        request.deviceListRequestPayload.type = DeviceUpdate_pb2.SPOT_DEVICE
        request.deviceListRequestPayload.id = str(uuid.uuid4())

        payload = request.SerializeToString()
        response_bytes = _nova_request(settings, NOVA_LIST_SCOPE, payload)

        device_list = DeviceUpdate_pb2.DevicesList()
        device_list.ParseFromString(response_bytes)

        devices: list[Device] = []
        for device_meta in device_list.deviceMetadata:
            name = device_meta.userDefinedDeviceName or "Unknown Device"

            if device_meta.identifierInformation.type == DeviceUpdate_pb2.IDENTIFIER_ANDROID:
                canonic_ids = device_meta.identifierInformation.phoneInformation.canonicIds.canonicId
                device_type = "Android"
            else:
                canonic_ids = device_meta.identifierInformation.canonicIds.canonicId
                device_type = "Tracker"

            manufacturer = ""
            model = ""
            if device_meta.HasField("information") and device_meta.information.HasField("deviceRegistration"):
                reg = device_meta.information.deviceRegistration
                manufacturer = reg.manufacturer
                model = reg.model

            locations: list[DeviceLocation] = []
            if (
                device_meta.HasField("information")
                and device_meta.information.HasField("locationInformation")
                and device_meta.information.locationInformation.HasField("reports")
                and device_meta.information.locationInformation.reports.HasField("recentLocationAndNetworkLocations")
            ):
                recent = device_meta.information.locationInformation.reports.recentLocationAndNetworkLocations
                if recent.HasField("recentLocation"):
                    ts = recent.recentLocationTimestamp if recent.HasField("recentLocationTimestamp") else None
                    loc = _parse_location_report(recent.recentLocation, ts)
                    if loc:
                        locations.append(loc)

            for canonic_id in canonic_ids:
                devices.append(
                    Device(
                        name=name,
                        canonic_id=canonic_id.id,
                        device_type=device_type,
                        manufacturer=manufacturer,
                        model=model,
                        locations=locations,
                    )
                )

        logger.info("Found %d device(s)", len(devices))
        return devices


def ring_device(settings: Settings, canonic_id: str, *, stop: bool = False) -> bool:
    """Ring (or stop ringing) a device.

    Args:
        settings: Application settings
        canonic_id: The device's canonic ID
        stop: If True, stop ringing instead of starting
    """
    action_name = "stop_ring" if stop else "ring"
    with trace_span(f"api.{action_name}", attributes={"device.canonic_id": canonic_id}):
        request = DeviceUpdate_pb2.ExecuteActionRequest()
        request.scope.type = DeviceUpdate_pb2.SPOT_DEVICE
        request.scope.device.canonicId.id = canonic_id

        request.requestMetadata.type = DeviceUpdate_pb2.SPOT_DEVICE
        request.requestMetadata.requestUuid = str(uuid.uuid4())
        request.requestMetadata.fmdClientUuid = str(uuid.uuid4())
        request.requestMetadata.gcmRegistrationId.id = ""
        request.requestMetadata.unknown = True

        if stop:
            request.action.stopSound.component = DeviceUpdate_pb2.DEVICE_COMPONENT_UNSPECIFIED
        else:
            request.action.startSound.component = DeviceUpdate_pb2.DEVICE_COMPONENT_UNSPECIFIED

        payload = request.SerializeToString()

        try:
            _nova_request(settings, NOVA_ACTION_SCOPE, payload)
            logger.info("Device %s command sent for %s", action_name, canonic_id)
            return True
        except RuntimeError:
            logger.exception("Failed to send %s command", action_name)
            return False
