"""Type stubs for generated protobuf module."""

from typing import Any

# Status enum
SEMANTIC: int
LAST_KNOWN: int
CROWDSOURCED: int
AGGREGATED: int

class Time:
    seconds: int
    nanos: int

class LocationReport:
    semanticLocation: Any
    geoLocation: Any
    status: int
    def HasField(self, field_name: str) -> bool: ...
    def SerializeToString(self) -> bytes: ...
    def ParseFromString(self, data: bytes) -> int: ...

class SemanticLocation:
    locationName: str

class GeoLocation:
    encryptedReport: Any
    deviceTimeOffset: int
    accuracy: float
    def HasField(self, field_name: str) -> bool: ...

class EncryptedReport:
    publicKeyRandom: bytes
    encryptedLocation: bytes
    isOwnReport: bool

def __getattr__(name: str) -> Any: ...
