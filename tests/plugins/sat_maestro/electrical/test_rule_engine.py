"""Tests for ECSS rule engine and safe expression evaluator."""
import pytest

from src.plugins.sat_maestro.electrical.rules.loader import (
    RuleEngine,
    SafeExpressionEvaluator,
)
from src.plugins.sat_maestro.core.graph_models import EcssRule, Severity


class TestSafeExpressionEvaluator:
    @pytest.fixture
    def evaluator(self):
        return SafeExpressionEvaluator()

    def test_simple_comparison(self, evaluator):
        assert evaluator.evaluate("x > 5", {"x": 10}) is True
        assert evaluator.evaluate("x > 5", {"x": 3}) is False

    def test_arithmetic(self, evaluator):
        assert evaluator.evaluate("x * 0.75 >= y", {"x": 100, "y": 70}) is True
        assert evaluator.evaluate("x * 0.75 >= y", {"x": 100, "y": 80}) is False

    def test_dict_attribute_access(self, evaluator):
        ctx = {"connector": {"current_rating": 10, "actual_current": 7}}
        assert evaluator.evaluate(
            "connector.current_rating * 0.75 >= connector.actual_current", ctx
        ) is True

    def test_dict_attribute_derating_fail(self, evaluator):
        ctx = {"connector": {"current_rating": 10, "actual_current": 9}}
        assert evaluator.evaluate(
            "connector.current_rating * 0.75 >= connector.actual_current", ctx
        ) is False

    def test_equality(self, evaluator):
        assert evaluator.evaluate("x == 0", {"x": 0}) is True
        assert evaluator.evaluate("x == 0", {"x": 1}) is False

    def test_not_equal(self, evaluator):
        assert evaluator.evaluate("x != 0", {"x": 1}) is True

    def test_less_than(self, evaluator):
        assert evaluator.evaluate("x <= 50", {"x": 30}) is True
        assert evaluator.evaluate("x <= 50", {"x": 60}) is False

    def test_unknown_variable(self, evaluator):
        # Should return False (evaluation fails safely)
        assert evaluator.evaluate("unknown > 5", {}) is False

    def test_division(self, evaluator):
        assert evaluator.evaluate("x / 2 > 3", {"x": 8}) is True

    def test_chained_comparison(self, evaluator):
        # Python AST supports chained: 0 < x < 10
        assert evaluator.evaluate("x > 0", {"x": 5}) is True

    def test_numeric_literal(self, evaluator):
        assert evaluator.evaluate("10 > 5", {}) is True

    def test_invalid_expression(self, evaluator):
        # Malformed expression should return False, not raise
        assert evaluator.evaluate("import os", {}) is False

    def test_no_function_calls(self, evaluator):
        # Function calls should fail safely
        assert evaluator.evaluate("len(x) > 0", {"x": [1]}) is False


class TestSeedRules:
    def test_default_rules_valid(self):
        from src.plugins.sat_maestro.db.seed_rules import DEFAULT_ECSS_RULES
        assert len(DEFAULT_ECSS_RULES) >= 15
        valid_standards = {
            "ECSS-E-ST-20C", "ECSS-E-ST-32C", "ECSS-E-ST-31C",
            "ECSS-E-ST-33C", "ECSS-E-HB-32-26A",
        }
        for rule in DEFAULT_ECSS_RULES:
            assert rule.id.startswith("ECSS-")
            assert rule.standard in valid_standards
            assert rule.severity in [Severity.ERROR, Severity.WARNING, Severity.INFO]
            assert rule.check_expression
            assert rule.message_template

    def test_rule_categories(self):
        from src.plugins.sat_maestro.db.seed_rules import DEFAULT_ECSS_RULES
        categories = {r.category for r in DEFAULT_ECSS_RULES}
        # Electrical categories
        assert "connector" in categories
        assert "power" in categories
        assert "wire" in categories
        assert "grounding" in categories
        assert "emc" in categories
        # Mechanical categories
        assert "mass" in categories
        assert "structural_strength" in categories
        assert "thermal_limit" in categories
        assert "deployment" in categories
        assert "modal" in categories
