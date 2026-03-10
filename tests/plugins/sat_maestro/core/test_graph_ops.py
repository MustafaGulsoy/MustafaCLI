"""Tests for graph operations."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.graph_models import (
    Component,
    ComponentType,
    Connector,
    EcssRule,
    Net,
    NetType,
    Pin,
    PinDirection,
    Severity,
)
from src.plugins.sat_maestro.core.graph_ops import GraphOperations


class TestComponentOps:
    @pytest.mark.asyncio
    async def test_create_component(self, graph_ops):
        graph_ops._client.execute_write = AsyncMock(return_value=[{"id": "C1"}])
        comp = Component(id="C1", name="MCU", type=ComponentType.IC, subsystem="OBC")
        result = await graph_ops.create_component(comp)
        assert result == "C1"
        graph_ops._client.execute_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_component_found(self, graph_ops):
        graph_ops._client.execute = AsyncMock(return_value=[{
            "c": {"id": "C1", "name": "MCU", "type": "IC", "subsystem": "OBC"}
        }])
        comp = await graph_ops.get_component("C1")
        assert comp is not None
        assert comp.name == "MCU"

    @pytest.mark.asyncio
    async def test_get_component_not_found(self, graph_ops):
        graph_ops._client.execute = AsyncMock(return_value=[])
        comp = await graph_ops.get_component("NONEXISTENT")
        assert comp is None


class TestPinOps:
    @pytest.mark.asyncio
    async def test_add_pin(self, graph_ops):
        graph_ops._client.execute_write = AsyncMock(return_value=[{"id": "P1"}])
        pin = Pin(id="P1", name="VCC", direction=PinDirection.POWER, voltage=3.3)
        result = await graph_ops.add_pin("C1", pin)
        assert result == "P1"

    @pytest.mark.asyncio
    async def test_get_pins(self, graph_ops):
        graph_ops._client.execute = AsyncMock(return_value=[
            {"p": {"id": "P1", "name": "VCC", "direction": "POWER", "voltage": 3.3, "current_max": 0.5}}
        ])
        pins = await graph_ops.get_pins("C1")
        assert len(pins) == 1
        assert pins[0].direction == PinDirection.POWER


class TestConnectionOps:
    @pytest.mark.asyncio
    async def test_connect_pins(self, graph_ops):
        graph_ops._client.execute_write = AsyncMock(return_value=[])
        await graph_ops.connect_pins("P1", "P2", "NET_VCC")
        graph_ops._client.execute_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_path(self, graph_ops):
        graph_ops._client.execute = AsyncMock(return_value=[
            {"node_ids": ["P1", "P2", "P3"], "nets": ["NET1", "NET2"]}
        ])
        paths = await graph_ops.find_path("P1", "P3")
        assert len(paths) == 1
        assert "P2" in paths[0]["node_ids"]


class TestEcssRuleOps:
    @pytest.mark.asyncio
    async def test_load_rules(self, graph_ops):
        graph_ops._client.execute_write = AsyncMock(return_value=[{"id": "R1"}])
        rules = [
            EcssRule(
                id="R1", standard="ECSS-E-ST-20C", clause="5.3.1",
                severity=Severity.ERROR, category="connector",
                check_expression="x > 0", message_template="test",
            )
        ]
        count = await graph_ops.load_ecss_rules(rules)
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_rules_by_category(self, graph_ops):
        graph_ops._client.execute = AsyncMock(return_value=[{
            "r": {
                "id": "R1", "standard": "ECSS", "clause": "5.3",
                "severity": "ERROR", "category": "connector",
                "check_expression": "x > 0", "message_template": "test",
            }
        }])
        rules = await graph_ops.get_ecss_rules(category="connector")
        assert len(rules) == 1
        assert rules[0].category == "connector"
