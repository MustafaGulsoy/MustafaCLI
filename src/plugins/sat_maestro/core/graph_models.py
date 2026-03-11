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


# -- Mechanical enums --

class JointType(str, Enum):
    REVOLUTE = "REVOLUTE"
    PRISMATIC = "PRISMATIC"
    FIXED = "FIXED"
    SPHERICAL = "SPHERICAL"


class MechanismType(str, Enum):
    HINGE = "HINGE"
    LATCH = "LATCH"
    MOTOR = "MOTOR"
    SPRING = "SPRING"
    DAMPER = "DAMPER"


class LoadCaseType(str, Enum):
    QUASI_STATIC = "QUASI_STATIC"
    RANDOM_VIB = "RANDOM_VIB"
    SHOCK = "SHOCK"
    THERMAL_CYCLE = "THERMAL_CYCLE"
    SINE_VIB = "SINE_VIB"


class ConductanceType(str, Enum):
    CONDUCTION = "CONDUCTION"
    RADIATION = "RADIATION"
    CONVECTION = "CONVECTION"


# -- Mechanical dataclasses --

@dataclass
class Material:
    """Material definition for structural/thermal analysis."""
    id: str
    name: str
    density: float  # kg/m3
    youngs_modulus: float = 0.0  # Pa
    poisson: float = 0.0
    thermal_conductivity: float = 0.0  # W/(m*K)
    cte: float = 0.0  # coefficient of thermal expansion, 1/K
    yield_strength: float = 0.0  # Pa
    ultimate_strength: float = 0.0  # Pa
    specific_heat: float = 0.0  # J/(kg*K)


@dataclass
class Structure:
    """Structural element (panel, bracket, beam)."""
    id: str
    name: str
    material: str  # material id or name
    mass: float  # kg
    volume: float = 0.0  # m3
    cog_x: float = 0.0
    cog_y: float = 0.0
    cog_z: float = 0.0
    subsystem: str = ""


@dataclass
class Assembly:
    """Assembly group (subsystem level)."""
    id: str
    name: str
    total_mass: float = 0.0  # kg
    cog_x: float = 0.0
    cog_y: float = 0.0
    cog_z: float = 0.0
    level: int = 0  # 0 = spacecraft, 1 = subsystem, 2 = unit...


@dataclass
class ThermalNode:
    """Thermal node for lumped-parameter model."""
    id: str
    name: str
    temperature: float = 20.0  # deg C
    capacity: float = 0.0  # J/K (thermal mass)
    power_dissipation: float = 0.0  # W
    op_min_temp: float = -40.0  # deg C operational min
    op_max_temp: float = 85.0  # deg C operational max


@dataclass
class ThermalConductance:
    """Thermal link between two nodes."""
    id: str
    node_a_id: str
    node_b_id: str
    type: ConductanceType = ConductanceType.CONDUCTION
    value: float = 0.0  # W/K


@dataclass
class Mechanism:
    """Deployment mechanism."""
    id: str
    name: str
    type: MechanismType
    state: str = "stowed"  # stowed / deploying / deployed
    dof: int = 1  # degrees of freedom


@dataclass
class Joint:
    """Mechanism joint."""
    id: str
    type: JointType
    min_angle: float = 0.0  # degrees
    max_angle: float = 360.0  # degrees
    torque: float = 0.0  # N*m (available torque)
    friction_torque: float = 0.0  # N*m
    structure_a_id: str = ""
    structure_b_id: str = ""


@dataclass
class FemModel:
    """FEM analysis model reference."""
    id: str
    name: str
    solver: str  # calculix / nastran
    node_count: int = 0
    element_count: int = 0
    solution_type: str = ""  # modal / static / thermal / buckling


@dataclass
class FemResult:
    """FEM result set."""
    id: str
    type: str  # modal / static / thermal
    max_stress: float = 0.0  # Pa
    max_displacement: float = 0.0  # m
    safety_factor: float = 0.0
    frequencies: list[float] = field(default_factory=list)  # Hz (for modal)
    mode_shapes: list[dict] = field(default_factory=list)


@dataclass
class LoadCase:
    """Load case definition."""
    id: str
    name: str
    type: LoadCaseType
    magnitude: float = 0.0  # g for quasi-static, gRMS for random, etc.
    direction: str = ""  # X, Y, Z, or combination
    duration: float = 0.0  # seconds
    psd_profile: list[tuple[float, float]] = field(default_factory=list)  # (Hz, g2/Hz)
