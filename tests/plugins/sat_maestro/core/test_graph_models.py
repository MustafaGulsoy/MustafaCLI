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
