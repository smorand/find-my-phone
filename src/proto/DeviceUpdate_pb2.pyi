"""Type stubs for generated protobuf module."""

from typing import Any

# Device types
UNKNOWN_DEVICE_TYPE: int
ANDROID_DEVICE: int
SPOT_DEVICE: int
TEST_DEVICE_TYPE: int
AUTO_DEVICE: int
FASTPAIR_DEVICE: int
SUPERVISED_ANDROID_DEVICE: int

# Identifier types
IDENTIFIER_UNKNOWN: int
IDENTIFIER_ANDROID: int
IDENTIFIER_SPOT: int

# Device components
DEVICE_COMPONENT_UNSPECIFIED: int
DEVICE_COMPONENT_RIGHT: int
DEVICE_COMPONENT_LEFT: int
DEVICE_COMPONENT_CASE: int

# Spot contributor types
FMDN_DISABLED_DEFAULT: int
FMDN_CONTRIBUTOR_HIGH_TRAFFIC: int
FMDN_CONTRIBUTOR_ALL_LOCATIONS: int
FMDN_HIGH_TRAFFIC: int
FMDN_ALL_LOCATIONS: int

class DevicesListRequest:
    deviceListRequestPayload: Any
    def SerializeToString(self) -> bytes: ...

class DevicesList:
    deviceMetadata: Any
    def ParseFromString(self, data: bytes) -> int: ...

class ExecuteActionRequest:
    scope: Any
    action: Any
    requestMetadata: Any
    def SerializeToString(self) -> bytes: ...

class DeviceUpdate:
    fcmMetadata: Any
    deviceMetadata: Any
    requestMetadata: Any
    def ParseFromString(self, data: bytes) -> int: ...

class Location:
    latitude: int
    longitude: int
    altitude: int
    def SerializeToString(self) -> bytes: ...
    def ParseFromString(self, data: bytes) -> int: ...

def __getattr__(name: str) -> Any: ...
