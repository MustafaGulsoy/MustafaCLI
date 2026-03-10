"""ECSS rule loader and safe expression evaluator."""
from __future__ import annotations

import ast
import logging
import operator
from typing import Any

from ...core.graph_models import EcssRule, Severity, Violation
from ...core.graph_ops import GraphOperations

logger = logging.getLogger(__name__)

# Safe operators for expression evaluation
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


class SafeExpressionEvaluator:
    """Evaluate ECSS rule expressions safely without eval/exec."""

    def evaluate(self, expression: str, context: dict[str, Any]) -> bool:
        """Evaluate a comparison expression with the given context.

        Supports: arithmetic (+, -, *, /), comparisons (>, <, >=, <=, ==, !=),
        attribute access (obj.attr), numeric literals.

        Does NOT support: function calls, imports, assignments, loops.
        """
        try:
            tree = ast.parse(expression, mode="eval")
            return bool(self._eval_node(tree.body, context))
        except Exception as e:
            logger.warning("Expression evaluation failed: %s - %s", expression, e)
            return False

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> Any:
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op_node, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                op_func = _SAFE_OPS.get(type(op_node))
                if op_func is None:
                    raise ValueError(f"Unsupported operator: {type(op_node).__name__}")
                if not op_func(left, right):
                    return False
                left = right
            return True

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op_func(left, right)

        elif isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.Name):
            if node.id not in context:
                raise ValueError(f"Unknown variable: {node.id}")
            return context[node.id]

        elif isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value, context)
            if isinstance(obj, dict):
                return obj.get(node.attr, 0)
            return getattr(obj, node.attr, 0)

        else:
            raise ValueError(f"Unsupported AST node: {type(node).__name__}")


class RuleEngine:
    """Load and evaluate ECSS rules from Neo4j."""

    def __init__(self, graph: GraphOperations) -> None:
        self._graph = graph
        self._evaluator = SafeExpressionEvaluator()

    async def load_rules(self, category: str | None = None) -> list[EcssRule]:
        """Load rules from Neo4j, optionally filtered by category."""
        return await self._graph.get_ecss_rules(category)

    async def evaluate_rule(self, rule: EcssRule, context: dict[str, Any]) -> Violation | None:
        """Evaluate a single rule against a context. Returns Violation if rule fails."""
        result = self._evaluator.evaluate(rule.check_expression, context)
        if not result:
            # Rule check failed - generate violation
            message = rule.message_template
            try:
                message = rule.message_template.format(**self._flatten_context(context))
            except (KeyError, IndexError):
                pass

            return Violation(
                rule_id=rule.id,
                severity=rule.severity,
                message=message,
                component_path=context.get("component_path", "unknown"),
                details={"rule_clause": rule.clause, "context": str(context)},
            )
        return None

    async def run_all(self, subsystem: str | None = None) -> list[Violation]:
        """Run all applicable ECSS rules and collect violations."""
        rules = await self.load_rules()
        violations: list[Violation] = []

        # Get components to check
        if subsystem:
            components = await self._graph.get_components_by_subsystem(subsystem)
        else:
            # Get all components
            try:
                result = await self._graph._client.execute(
                    "MATCH (c:Component) RETURN c"
                )
                from ...core.graph_models import Component, ComponentType
                components = [
                    Component(
                        id=r["c"]["id"],
                        name=r["c"]["name"],
                        type=ComponentType(r["c"]["type"]),
                        subsystem=r["c"].get("subsystem", ""),
                    )
                    for r in result
                ]
            except Exception:
                components = []

        for comp in components:
            pins = await self._graph.get_pins(comp.id)
            for rule in rules:
                # Build context for each component
                for pin in pins:
                    context = {
                        "component": {
                            "name": comp.name,
                            "type": comp.type.value,
                            "subsystem": comp.subsystem,
                        },
                        "pin": {
                            "name": pin.name,
                            "direction": pin.direction.value,
                            "voltage": pin.voltage or 0,
                            "current_max": pin.current_max or 0,
                            "actual_current": pin.actual_current or 0,
                        },
                        "connector": {
                            "current_rating": 0,
                            "actual_current": pin.actual_current or 0,
                        },
                        "component_path": f"{comp.id}/{pin.id}",
                        "name": comp.name,
                    }
                    violation = await self.evaluate_rule(rule, context)
                    if violation:
                        violations.append(violation)

        return violations

    @staticmethod
    def _flatten_context(context: dict) -> dict:
        """Flatten nested dict for string formatting."""
        flat = {}
        for key, value in context.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    flat[f"{key}_{k}"] = v
                    flat[k] = v  # Also add without prefix for convenience
            else:
                flat[key] = value
        return flat
