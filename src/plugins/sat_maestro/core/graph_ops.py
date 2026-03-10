"""Graph operations for satellite component management."""
from __future__ import annotations

import logging
from typing import Any

from .graph_models import (
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
from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class GraphOperations:
    """CRUD operations on the satellite knowledge graph."""

    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    # -- Component operations --

    async def create_component(self, component: Component) -> str:
        """Create a component node and return its id."""
        query = """
        CREATE (c:Component {
            id: $id, name: $name, type: $type,
            subsystem: $subsystem, properties: $properties
        })
        RETURN c.id AS id
        """
        result = await self._client.execute_write(query, {
            "id": component.id,
            "name": component.name,
            "type": component.type.value,
            "subsystem": component.subsystem,
            "properties": str(component.properties),
        })
        return result[0]["id"] if result else component.id

    async def get_component(self, component_id: str) -> Component | None:
        """Get a component by ID."""
        query = "MATCH (c:Component {id: $id}) RETURN c"
        result = await self._client.execute(query, {"id": component_id})
        if not result:
            return None
        node = result[0]["c"]
        return Component(
            id=node["id"],
            name=node["name"],
            type=ComponentType(node["type"]),
            subsystem=node["subsystem"],
        )

    async def get_components_by_subsystem(self, subsystem: str) -> list[Component]:
        """Get all components in a subsystem."""
        query = "MATCH (c:Component {subsystem: $subsystem}) RETURN c"
        result = await self._client.execute(query, {"subsystem": subsystem})
        return [
            Component(
                id=r["c"]["id"],
                name=r["c"]["name"],
                type=ComponentType(r["c"]["type"]),
                subsystem=r["c"]["subsystem"],
            )
            for r in result
        ]

    # -- Pin operations --

    async def add_pin(self, component_id: str, pin: Pin) -> str:
        """Add a pin to a component."""
        query = """
        MATCH (c:Component {id: $comp_id})
        CREATE (p:Pin {
            id: $id, name: $name, direction: $direction,
            voltage: $voltage, current_max: $current_max
        })
        CREATE (c)-[:HAS_PIN]->(p)
        RETURN p.id AS id
        """
        result = await self._client.execute_write(query, {
            "comp_id": component_id,
            "id": pin.id,
            "name": pin.name,
            "direction": pin.direction.value,
            "voltage": pin.voltage,
            "current_max": pin.current_max,
        })
        return result[0]["id"] if result else pin.id

    async def get_pins(self, component_id: str) -> list[Pin]:
        """Get all pins for a component."""
        query = """
        MATCH (c:Component {id: $comp_id})-[:HAS_PIN]->(p:Pin)
        RETURN p
        """
        result = await self._client.execute(query, {"comp_id": component_id})
        return [
            Pin(
                id=r["p"]["id"],
                name=r["p"]["name"],
                direction=PinDirection(r["p"]["direction"]),
                component_id=component_id,
                voltage=r["p"].get("voltage"),
                current_max=r["p"].get("current_max"),
            )
            for r in result
        ]

    # -- Connection operations --

    async def connect_pins(self, pin1_id: str, pin2_id: str, net_name: str, trace_width: float | None = None) -> None:
        """Create a CONNECTED_TO relationship between two pins."""
        query = """
        MATCH (p1:Pin {id: $pin1_id}), (p2:Pin {id: $pin2_id})
        CREATE (p1)-[:CONNECTED_TO {net_name: $net_name, trace_width: $trace_width}]->(p2)
        """
        await self._client.execute_write(query, {
            "pin1_id": pin1_id,
            "pin2_id": pin2_id,
            "net_name": net_name,
            "trace_width": trace_width,
        })

    async def find_path(self, pin1_id: str, pin2_id: str) -> list[dict]:
        """Find connection path between two pins."""
        query = """
        MATCH path = (p1:Pin {id: $pin1_id})-[:CONNECTED_TO*]-(p2:Pin {id: $pin2_id})
        RETURN [n IN nodes(path) | n.id] AS node_ids,
               [r IN relationships(path) | r.net_name] AS nets
        LIMIT 1
        """
        return await self._client.execute(query, {
            "pin1_id": pin1_id,
            "pin2_id": pin2_id,
        })

    async def get_all_connections(self) -> list[dict]:
        """Get all pin-to-pin connections."""
        query = """
        MATCH (p1:Pin)-[r:CONNECTED_TO]->(p2:Pin)
        RETURN p1.id AS from_pin, p2.id AS to_pin, r.net_name AS net_name
        """
        return await self._client.execute(query)

    # -- Net operations --

    async def create_net(self, net: Net) -> str:
        """Create a net node."""
        query = """
        CREATE (n:Net {id: $id, name: $name, type: $type})
        RETURN n.id AS id
        """
        result = await self._client.execute_write(query, {
            "id": net.id,
            "name": net.name,
            "type": net.type.value,
        })
        return result[0]["id"] if result else net.id

    async def link_net_to_pin(self, net_id: str, pin_id: str) -> None:
        """Create a CARRIES relationship from net to pin."""
        query = """
        MATCH (n:Net {id: $net_id}), (p:Pin {id: $pin_id})
        CREATE (n)-[:CARRIES]->(p)
        """
        await self._client.execute_write(query, {"net_id": net_id, "pin_id": pin_id})

    # -- Connector operations --

    async def create_connector(self, connector: Connector) -> str:
        """Create a connector node."""
        query = """
        CREATE (c:Connector {
            id: $id, name: $name, pin_count: $pin_count,
            series: $series, current_rating: $current_rating
        })
        RETURN c.id AS id
        """
        result = await self._client.execute_write(query, {
            "id": connector.id,
            "name": connector.name,
            "pin_count": connector.pin_count,
            "series": connector.series,
            "current_rating": connector.current_rating,
        })
        return result[0]["id"] if result else connector.id

    async def mate_connectors(self, conn1_id: str, conn2_id: str) -> None:
        """Create MATES_WITH relationship between connectors."""
        query = """
        MATCH (c1:Connector {id: $c1_id}), (c2:Connector {id: $c2_id})
        CREATE (c1)-[:MATES_WITH]->(c2)
        """
        await self._client.execute_write(query, {"c1_id": conn1_id, "c2_id": conn2_id})

    # -- ECSS Rule operations --

    async def load_ecss_rules(self, rules: list[EcssRule]) -> int:
        """Load ECSS rules into the graph. Returns count of rules loaded."""
        count = 0
        for rule in rules:
            query = """
            MERGE (r:EcssRule {id: $id})
            SET r.standard = $standard,
                r.clause = $clause,
                r.severity = $severity,
                r.category = $category,
                r.check_expression = $check_expression,
                r.message_template = $message_template
            RETURN r.id AS id
            """
            await self._client.execute_write(query, {
                "id": rule.id,
                "standard": rule.standard,
                "clause": rule.clause,
                "severity": rule.severity.value,
                "category": rule.category,
                "check_expression": rule.check_expression,
                "message_template": rule.message_template,
            })
            count += 1
        return count

    async def get_ecss_rules(self, category: str | None = None) -> list[EcssRule]:
        """Get ECSS rules, optionally filtered by category."""
        if category:
            query = "MATCH (r:EcssRule {category: $category}) RETURN r"
            result = await self._client.execute(query, {"category": category})
        else:
            query = "MATCH (r:EcssRule) RETURN r"
            result = await self._client.execute(query)

        return [
            EcssRule(
                id=r["r"]["id"],
                standard=r["r"]["standard"],
                clause=r["r"]["clause"],
                severity=Severity(r["r"]["severity"]),
                category=r["r"]["category"],
                check_expression=r["r"]["check_expression"],
                message_template=r["r"]["message_template"],
            )
            for r in result
        ]

    # -- Violation operations --

    async def store_analysis_run(self, result: AnalysisResult, run_id: str) -> str:
        """Store an analysis run and its violations in the graph."""
        query = """
        CREATE (run:AnalysisRun {
            id: $id, analyzer: $analyzer, status: $status,
            timestamp: $timestamp
        })
        RETURN run.id AS id
        """
        await self._client.execute_write(query, {
            "id": run_id,
            "analyzer": result.analyzer,
            "status": result.status.value,
            "timestamp": result.timestamp.isoformat(),
        })

        for v in result.violations:
            v_query = """
            MATCH (run:AnalysisRun {id: $run_id})
            CREATE (v:Violation {
                rule_id: $rule_id, severity: $severity,
                message: $message, component_path: $component_path
            })
            CREATE (run)-[:FOUND]->(v)
            """
            await self._client.execute_write(v_query, {
                "run_id": run_id,
                "rule_id": v.rule_id,
                "severity": v.severity.value,
                "message": v.message,
                "component_path": v.component_path,
            })

        return run_id

    async def clear_graph(self) -> None:
        """Delete all nodes and relationships. Use with caution."""
        await self._client.execute_write("MATCH (n) DETACH DELETE n")
