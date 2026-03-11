"""Tests for graph data models."""
from datetime import datetime

from src.plugins.sat_maestro.core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Component,
    ComponentType,
    Connector,
    EcssRule,
    Net,
    NetType,
    Pin,
    PinDirection,
    Severity,
    Violation,
)


class TestComponent:
    def test_create_component(self):
        c = Component(id="C1", name="MCU", type=ComponentType.IC, subsystem="OBC")
        assert c.id == "C1"
        assert c.type == ComponentType.IC

    def test_component_with_properties(self):
        c = Component(
            id="C2", name="Resistor", type=ComponentType.PASSIVE,
            subsystem="EPS", properties={"resistance": "10k"}
        )
        assert c.properties["resistance"] == "10k"


class TestPin:
    def test_create_pin(self):
        p = Pin(id="P1", name="VCC", direction=PinDirection.POWER, voltage=3.3, current_max=0.5)
        assert p.voltage == 3.3
        assert p.current_max == 0.5

    def test_pin_defaults(self):
        p = Pin(id="P2", name="GPIO0", direction=PinDirection.OUTPUT)
        assert p.voltage is None
        assert p.actual_current is None


class TestAnalysisResult:
    def test_pass_result(self):
        r = AnalysisResult(analyzer="pin_to_pin", status=AnalysisStatus.PASS)
        assert not r.has_errors
        assert not r.has_warnings

    def test_fail_result_with_violations(self):
        v = Violation(
            rule_id="ECSS-001", severity=Severity.ERROR,
            message="Derating exceeded", component_path="J4"
        )
        r = AnalysisResult(
            analyzer="connector", status=AnalysisStatus.FAIL, violations=[v]
        )
        assert r.has_errors
        assert len(r.violations) == 1

    def test_warn_result(self):
        v = Violation(
            rule_id="ECSS-002", severity=Severity.WARNING,
            message="Low margin", component_path="REG1"
        )
        r = AnalysisResult(
            analyzer="power_budget", status=AnalysisStatus.WARN, violations=[v]
        )
        assert r.has_warnings
        assert not r.has_errors


class TestEcssRule:
    def test_create_rule(self):
        rule = EcssRule(
            id="ECSS-E-ST-20C-5.3.1",
            standard="ECSS-E-ST-20C",
            clause="5.3.1",
            severity=Severity.ERROR,
            category="connector",
            check_expression="connector.current_rating * 0.75 >= connector.actual_current",
            message_template="Connector {name} exceeds 75% derating limit",
        )
        assert rule.category == "connector"
        assert rule.severity == Severity.ERROR


from src.plugins.sat_maestro.core.graph_models import (
    Structure, Assembly, ThermalNode, ThermalConductance,
    Mechanism, Joint, FemModel, FemResult, Material, LoadCase,
    JointType, MechanismType, LoadCaseType, ConductanceType,
)


class TestMechanicalModels:

    def test_structure_creation(self):
        s = Structure(id="str-1", name="Top Panel", material="Al-7075",
                      mass=2.5, volume=0.001, cog_x=0.0, cog_y=0.0, cog_z=0.5)
        assert s.mass == 2.5
        assert s.material == "Al-7075"

    def test_assembly_contains_structures(self):
        a = Assembly(id="asm-1", name="Spacecraft Bus", total_mass=50.0, level=0)
        assert a.total_mass == 50.0
        assert a.level == 0

    def test_thermal_node(self):
        tn = ThermalNode(id="tn-1", name="Battery Pack", temperature=25.0,
                         capacity=500.0, power_dissipation=3.0)
        assert tn.power_dissipation == 3.0

    def test_mechanism(self):
        m = Mechanism(id="mech-1", name="Solar Array Drive", type=MechanismType.MOTOR,
                      state="stowed", dof=1)
        assert m.type == MechanismType.MOTOR

    def test_joint(self):
        j = Joint(id="jnt-1", type=JointType.REVOLUTE, min_angle=0.0,
                  max_angle=180.0, torque=5.0)
        assert j.max_angle == 180.0

    def test_material(self):
        m = Material(id="mat-1", name="Al-7075-T6", density=2810.0,
                     youngs_modulus=71.7e9, poisson=0.33,
                     thermal_conductivity=130.0, cte=23.6e-6,
                     yield_strength=503e6)
        assert m.density == 2810.0

    def test_fem_model(self):
        fm = FemModel(id="fem-1", name="Bus Modal", solver="calculix",
                      node_count=15000, element_count=45000,
                      solution_type="modal")
        assert fm.solver == "calculix"

    def test_fem_result(self):
        fr = FemResult(id="res-1", type="modal", max_stress=0.0,
                       max_displacement=0.0, safety_factor=0.0,
                       frequencies=[35.2, 48.7, 62.1])
        assert len(fr.frequencies) == 3

    def test_load_case(self):
        lc = LoadCase(id="lc-1", name="Launch Quasi-Static",
                      type=LoadCaseType.QUASI_STATIC, magnitude=15.0)
        assert lc.type == LoadCaseType.QUASI_STATIC
