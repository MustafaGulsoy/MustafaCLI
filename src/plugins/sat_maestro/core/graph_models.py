"""Graph data models for satellite digital twin representation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ComponentType(str, Enum):
    IC = "IC"
    CONNECTOR = "CONNECTOR"
    PASSIVE = "PASSIVE"
    MODULE = "MODULE"


class PinDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    POWER = "POWER"


class NetType(str, Enum):
    POWER = "POWER"
    SIGNAL = "SIGNAL"
    GROUND = "GROUND"


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class AnalysisStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Component:
    id: str
    name: str
    type: ComponentType
    subsystem: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Pin:
    id: str
    name: str
    direction: PinDirection
    component_id: str = ""
    voltage: float | None = None
    current_max: float | None = None
    actual_current: float | None = None


@dataclass
class Net:
    id: str
    name: str
    type: NetType
    pin_ids: list[str] = field(default_factory=list)


@dataclass
class Connector:
    id: str
    name: str
    pin_count: int
    series: str = ""
    current_rating: float = 0.0
    mate_connector_id: str | None = None


@dataclass
class EcssRule:
    id: str
    standard: str
    clause: str
    severity: Severity
    category: str
    check_expression: str
    message_template: str


@dataclass
class Violation:
    rule_id: str
    severity: Severity
    message: str
    component_path: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Pad:
    """PCB pad from Gerber data."""
    id: str
    x: float
    y: float
    aperture: str
    layer: str = ""
    net_name: str = ""
    component_id: str = ""


@dataclass
class Trace:
    """PCB trace from Gerber data."""
    id: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width: float
    layer: str = ""
    net_name: str = ""


@dataclass
class AnalysisResult:
    analyzer: str
    status: AnalysisStatus
    timestamp: datetime = field(default_factory=datetime.now)
    violations: list[Violation] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    @property
    def has_warnings(self) -> bool:
        return any(v.severity == Severity.WARNING for v in self.violations)
