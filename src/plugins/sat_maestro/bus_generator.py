"""Electrical bus and thermal network generator for CubeSat designs.

Generates pin definitions, power/data/ground bus connections, and thermal
network nodes for a CubeSat design, writing everything to Neo4j via the
MCP bridge with idempotent MERGE operations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .core.graph_models import (
    ConductanceType,
    NetType,
    PinDirection,
)
from .core.mcp_bridge import McpBridge
from .cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pin templates — electrical interface definition for every catalog component
# ---------------------------------------------------------------------------

def _pin(
    name: str,
    direction: str = "POWER",
    voltage: float = 0.0,
    current_max: float = 0.5,
) -> dict[str, Any]:
    """Helper to build a pin template entry."""
    return {
        "name": name,
        "direction": direction,
        "voltage": voltage,
        "current_max": current_max,
    }


PIN_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "eps_pcu": [
        _pin("VIN", "INPUT", 8.5, 2.0),
        _pin("3V3_OUT", "OUTPUT", 3.3, 3.0),
        _pin("5V_OUT", "OUTPUT", 5.0, 4.0),
        _pin("BATT", "BIDIRECTIONAL", 7.4, 3.0),
        _pin("GND", "POWER", 0.0, 5.0),
        _pin("I2C_SDA", "BIDIRECTIONAL", 3.3, 0.01),
        _pin("I2C_SCL", "BIDIRECTIONAL", 3.3, 0.01),
    ],
    "eps_batt": [
        _pin("BATT_OUT", "OUTPUT", 7.4, 3.0),
        _pin("GND", "POWER", 0.0, 3.0),
    ],
    "eps_solar": [
        _pin("VOUT", "OUTPUT", 8.5, 1.0),
        _pin("GND", "POWER", 0.0, 1.0),
    ],
    "obc_main": [
        _pin("VCC", "INPUT", 3.3, 0.2),
        _pin("GND", "POWER", 0.0, 0.2),
        _pin("I2C_SDA", "BIDIRECTIONAL", 3.3, 0.01),
        _pin("I2C_SCL", "BIDIRECTIONAL", 3.3, 0.01),
        _pin("UART_TX", "OUTPUT", 3.3, 0.01),
        _pin("UART_RX", "INPUT", 3.3, 0.01),
        _pin("SPI_MOSI", "OUTPUT", 3.3, 0.01),
        _pin("SPI_MISO", "INPUT", 3.3, 0.01),
        _pin("SPI_CLK", "OUTPUT", 3.3, 0.01),
    ],
    "com_uhf_trx": [
        _pin("VCC", "INPUT", 5.0, 0.5),
        _pin("GND", "POWER", 0.0, 0.5),
        _pin("UART_TX", "OUTPUT", 3.3, 0.01),
        _pin("UART_RX", "INPUT", 3.3, 0.01),
    ],
    "com_uhf_ant": [
        _pin("RF_IN", "INPUT", 0.0, 0.0),
    ],
    "com_sband_tx": [
        _pin("VCC", "INPUT", 5.0, 1.5),
        _pin("GND", "POWER", 0.0, 1.5),
        _pin("SPI_MOSI", "INPUT", 3.3, 0.01),
        _pin("SPI_MISO", "OUTPUT", 3.3, 0.01),
        _pin("SPI_CLK", "INPUT", 3.3, 0.01),
    ],
    "com_sband_ant": [
        _pin("RF_IN", "INPUT", 0.0, 0.0),
    ],
    "adcs_unit": [
        _pin("VCC", "INPUT", 5.0, 0.2),
        _pin("GND", "POWER", 0.0, 0.2),
        _pin("I2C_SDA", "BIDIRECTIONAL", 3.3, 0.01),
        _pin("I2C_SCL", "BIDIRECTIONAL", 3.3, 0.01),
    ],
    "gps_rx": [
        _pin("VCC", "INPUT", 3.3, 0.1),
        _pin("GND", "POWER", 0.0, 0.1),
        _pin("I2C_SDA", "BIDIRECTIONAL", 3.3, 0.01),
        _pin("I2C_SCL", "BIDIRECTIONAL", 3.3, 0.01),
    ],
    "prop_unit": [
        _pin("VCC", "INPUT", 5.0, 0.25),
        _pin("GND", "POWER", 0.0, 0.25),
        _pin("I2C_SDA", "BIDIRECTIONAL", 3.3, 0.01),
        _pin("I2C_SCL", "BIDIRECTIONAL", 3.3, 0.01),
    ],
    "therm_heater": [
        _pin("VCC", "INPUT", 5.0, 0.5),
        _pin("GND", "POWER", 0.0, 0.5),
    ],
    "payload_main": [
        _pin("VCC", "INPUT", 5.0, 1.5),
        _pin("GND", "POWER", 0.0, 1.5),
        _pin("SPI_MOSI", "INPUT", 3.3, 0.01),
        _pin("SPI_MISO", "OUTPUT", 3.3, 0.01),
        _pin("SPI_CLK", "INPUT", 3.3, 0.01),
    ],
    "structure_frame": [],
}


# ---------------------------------------------------------------------------
# Bus connection rules — topology definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _BusConnection:
    """A single point-to-point or point-to-multi connection rule."""
    source_comp: str
    source_pin: str
    dest_comp: str
    dest_pin: str


@dataclass(frozen=True)
class _BusRule:
    """Named bus with its net type and constituent connections."""
    name: str
    net_type: NetType
    connections: tuple[_BusConnection, ...]


def _build_bus_rules() -> list[_BusRule]:
    """Construct the complete set of bus wiring rules."""
    rules: list[_BusRule] = []

    # -- Power buses --
    rules.append(_BusRule(
        name="SOLAR_BUS",
        net_type=NetType.POWER,
        connections=(
            _BusConnection("eps_solar", "VOUT", "eps_pcu", "VIN"),
        ),
    ))

    rules.append(_BusRule(
        name="BATT_BUS",
        net_type=NetType.POWER,
        connections=(
            _BusConnection("eps_batt", "BATT_OUT", "eps_pcu", "BATT"),
        ),
    ))

    # 3.3 V rail
    _3v3_targets = [
        ("obc_main", "VCC"),
        ("gps_rx", "VCC"),
    ]
    rules.append(_BusRule(
        name="3V3_BUS",
        net_type=NetType.POWER,
        connections=tuple(
            _BusConnection("eps_pcu", "3V3_OUT", comp, pin)
            for comp, pin in _3v3_targets
        ),
    ))

    # 5 V rail
    _5v_targets = [
        ("com_uhf_trx", "VCC"),
        ("com_sband_tx", "VCC"),
        ("adcs_unit", "VCC"),
        ("prop_unit", "VCC"),
        ("therm_heater", "VCC"),
        ("payload_main", "VCC"),
    ]
    rules.append(_BusRule(
        name="5V_BUS",
        net_type=NetType.POWER,
        connections=tuple(
            _BusConnection("eps_pcu", "5V_OUT", comp, pin)
            for comp, pin in _5v_targets
        ),
    ))

    # Ground bus — all GND pins star-connected
    _gnd_comps = [
        cid for cid, pins in PIN_TEMPLATES.items()
        if any(p["name"] == "GND" for p in pins)
    ]
    # Connect every component's GND to eps_pcu GND as star center
    rules.append(_BusRule(
        name="GND_BUS",
        net_type=NetType.GROUND,
        connections=tuple(
            _BusConnection(comp, "GND", "eps_pcu", "GND")
            for comp in _gnd_comps
            if comp != "eps_pcu"
        ),
    ))

    # -- Data buses --

    # I2C bus: OBC as controller
    _i2c_targets = ["eps_pcu", "adcs_unit", "gps_rx", "prop_unit"]
    i2c_conns: list[_BusConnection] = []
    for target in _i2c_targets:
        i2c_conns.append(_BusConnection("obc_main", "I2C_SDA", target, "I2C_SDA"))
        i2c_conns.append(_BusConnection("obc_main", "I2C_SCL", target, "I2C_SCL"))
    rules.append(_BusRule(
        name="I2C_BUS",
        net_type=NetType.SIGNAL,
        connections=tuple(i2c_conns),
    ))

    # UART UHF: crossover TX/RX
    rules.append(_BusRule(
        name="UART_UHF",
        net_type=NetType.SIGNAL,
        connections=(
            _BusConnection("obc_main", "UART_TX", "com_uhf_trx", "UART_RX"),
            _BusConnection("com_uhf_trx", "UART_TX", "obc_main", "UART_RX"),
        ),
    ))

    # SPI payload bus: OBC to payload + S-band
    _spi_targets = ["payload_main", "com_sband_tx"]
    spi_conns: list[_BusConnection] = []
    for target in _spi_targets:
        spi_conns.append(_BusConnection("obc_main", "SPI_MOSI", target, "SPI_MOSI"))
        spi_conns.append(_BusConnection(target, "SPI_MISO", "obc_main", "SPI_MISO"))
        spi_conns.append(_BusConnection("obc_main", "SPI_CLK", target, "SPI_CLK"))
    rules.append(_BusRule(
        name="SPI_PAYLOAD",
        net_type=NetType.SIGNAL,
        connections=tuple(spi_conns),
    ))

    # RF links
    rules.append(_BusRule(
        name="RF_UHF",
        net_type=NetType.SIGNAL,
        connections=(
            _BusConnection("com_uhf_trx", "UART_TX", "com_uhf_ant", "RF_IN"),
        ),
    ))

    rules.append(_BusRule(
        name="RF_SBAND",
        net_type=NetType.SIGNAL,
        connections=(
            _BusConnection("com_sband_tx", "SPI_MISO", "com_sband_ant", "RF_IN"),
        ),
    ))

    return rules


BUS_RULES: list[_BusRule] = _build_bus_rules()


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------

@dataclass
class BusGenerationResult:
    """Summary of what the bus generator created in Neo4j."""
    pins_created: int = 0
    nets_created: int = 0
    connections_created: int = 0
    thermal_nodes_created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Bus generator
# ---------------------------------------------------------------------------

class BusGenerator:
    """Generate electrical bus connections and thermal network in Neo4j.

    All Cypher writes use parameterized MERGE for idempotent operation,
    allowing safe re-runs without duplicating nodes or relationships.
    """

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    # -- Public API --

    async def generate(self, design: CubeSatDesign) -> BusGenerationResult:
        """Generate complete electrical bus network for a CubeSat design.

        Args:
            design: The CubeSat design containing selected subsystems.

        Returns:
            Summary counts of created graph elements.
        """
        result = BusGenerationResult()
        active_comp_ids = self._resolve_active_component_ids(design)

        logger.info(
            "Generating bus network for %d components: %s",
            len(active_comp_ids),
            ", ".join(sorted(active_comp_ids)),
        )

        # Build component lookup for power/voltage data
        comp_lookup = {c["id"]: c for c in design.get_all_components()}

        # Phase 1: Create Pin nodes and HAS_PIN relationships
        pins_created = await self._create_pins(active_comp_ids, comp_lookup)
        result.pins_created = pins_created

        # Phase 2: Create Net nodes and CONNECTED_TO relationships
        nets_created, conns_created = await self._create_buses(active_comp_ids)
        result.nets_created = nets_created
        result.connections_created = conns_created

        # Phase 3: Set actual_current on load pins
        await self._set_actual_currents(active_comp_ids, comp_lookup)

        logger.info(
            "Bus generation complete: %d pins, %d nets, %d connections",
            result.pins_created,
            result.nets_created,
            result.connections_created,
        )
        return result

    async def generate_thermal_network(self, design: CubeSatDesign) -> int:
        """Generate lumped-parameter thermal network in Neo4j.

        Creates a ThermalNode per component, a structure node, a deep-space
        boundary node, and conductive links between them.

        Args:
            design: The CubeSat design.

        Returns:
            Number of thermal nodes created.
        """
        components = design.get_all_components()
        node_count = 0

        # Phase 1: Create a ThermalNode for each component
        for comp in components:
            comp_id = comp["id"]
            power_w = comp["power_w"] if comp["power_w"] > 0 else 0.0
            mass_kg = comp["mass_g"] / 1000.0

            # Thermal capacity estimate: mass * specific_heat (Al ~900 J/(kg*K))
            capacity = mass_kg * 900.0

            await self._bridge.neo4j_write(
                "MERGE (tn:ThermalNode {id: $id}) "
                "SET tn.name = $name, "
                "    tn.temperature = $temperature, "
                "    tn.capacity = $capacity, "
                "    tn.power_dissipation = $power_dissipation, "
                "    tn.op_min_temp = $op_min, "
                "    tn.op_max_temp = $op_max",
                {
                    "id": f"thermal_{comp_id}",
                    "name": f"{comp['name']} (thermal)",
                    "temperature": 20.0,
                    "capacity": round(capacity, 4),
                    "power_dissipation": power_w,
                    "op_min": -40.0,
                    "op_max": 85.0,
                },
            )

            # Link ThermalNode to Component
            await self._bridge.neo4j_write(
                "MATCH (c:Component {id: $comp_id}), "
                "      (tn:ThermalNode {id: $tn_id}) "
                "MERGE (c)-[:HAS_THERMAL_NODE]->(tn)",
                {"comp_id": comp_id, "tn_id": f"thermal_{comp_id}"},
            )
            node_count += 1

        # Phase 2: Structure ThermalNode (large thermal mass, no power)
        struct_mass_kg = next(
            (c["mass_g"] / 1000.0 for c in components if c["id"] == "structure_frame"),
            0.1,
        )
        struct_capacity = struct_mass_kg * 900.0

        await self._bridge.neo4j_write(
            "MERGE (tn:ThermalNode {id: $id}) "
            "SET tn.name = $name, "
            "    tn.temperature = $temperature, "
            "    tn.capacity = $capacity, "
            "    tn.power_dissipation = 0.0, "
            "    tn.op_min_temp = -100.0, "
            "    tn.op_max_temp = 150.0",
            {
                "id": "thermal_structure",
                "name": "Structure (thermal)",
                "temperature": 20.0,
                "capacity": round(struct_capacity, 4),
            },
        )
        node_count += 1

        # Phase 3: Deep-space boundary node
        await self._bridge.neo4j_write(
            "MERGE (tn:ThermalNode {id: $id}) "
            "SET tn.name = $name, "
            "    tn.temperature = $temperature, "
            "    tn.capacity = $capacity, "
            "    tn.power_dissipation = 0.0, "
            "    tn.op_min_temp = -273.15, "
            "    tn.op_max_temp = -200.0",
            {
                "id": "thermal_space",
                "name": "Deep Space Boundary",
                "temperature": -270.0,
                "capacity": 1.0e12,
            },
        )
        node_count += 1

        # Phase 4: Thermal conductance links
        #   Component -> Structure: 2.0 W/K (conduction through PCB mounting + bolts)
        #   Structure -> Space:     0.15 W/K (radiation from 6 faces, emissivity ~0.85)
        link_count = 0
        for comp in components:
            if comp["id"] == "structure_frame":
                continue
            link_id = f"tc_{comp['id']}_to_structure"
            await self._bridge.neo4j_write(
                "MERGE (tc:ThermalConductance {id: $id}) "
                "SET tc.type = $type, "
                "    tc.value = $value, "
                "    tc.node_a_id = $node_a, "
                "    tc.node_b_id = $node_b "
                "WITH tc "
                "MATCH (a:ThermalNode {id: $node_a}), "
                "      (b:ThermalNode {id: $node_b}) "
                "MERGE (a)-[:CONDUCTS_TO {conductance_id: $id}]->(tc) "
                "MERGE (tc)-[:CONDUCTS_TO {conductance_id: $id}]->(b)",
                {
                    "id": link_id,
                    "type": ConductanceType.CONDUCTION.value,
                    "value": 2.0,
                    "node_a": f"thermal_{comp['id']}",
                    "node_b": "thermal_structure",
                },
            )
            link_count += 1

        # Structure -> Space radiation link
        await self._bridge.neo4j_write(
            "MERGE (tc:ThermalConductance {id: $id}) "
            "SET tc.type = $type, "
            "    tc.value = $value, "
            "    tc.node_a_id = $node_a, "
            "    tc.node_b_id = $node_b "
            "WITH tc "
            "MATCH (a:ThermalNode {id: $node_a}), "
            "      (b:ThermalNode {id: $node_b}) "
            "MERGE (a)-[:CONDUCTS_TO {conductance_id: $id}]->(tc) "
            "MERGE (tc)-[:CONDUCTS_TO {conductance_id: $id}]->(b)",
            {
                "id": "tc_structure_to_space",
                "type": ConductanceType.RADIATION.value,
                "value": 0.15,
                "node_a": "thermal_structure",
                "node_b": "thermal_space",
            },
        )

        logger.info(
            "Thermal network complete: %d nodes, %d conductance links",
            node_count,
            link_count + 1,
        )
        return node_count

    # -- Private helpers --

    def _resolve_active_component_ids(self, design: CubeSatDesign) -> set[str]:
        """Return the set of component IDs that are part of this design."""
        return {c["id"] for c in design.get_all_components()}

    async def _create_pins(
        self,
        active_ids: set[str],
        comp_lookup: dict[str, dict[str, Any]],
    ) -> int:
        """Create Pin nodes and (Component)-[:HAS_PIN]->(Pin) relationships."""
        count = 0
        for comp_id in sorted(active_ids):
            templates = PIN_TEMPLATES.get(comp_id, [])
            if not templates:
                continue

            for pin_tmpl in templates:
                pin_id = f"{comp_id}_{pin_tmpl['name']}"

                await self._bridge.neo4j_write(
                    "MERGE (p:Pin {id: $pin_id}) "
                    "SET p.name = $name, "
                    "    p.direction = $direction, "
                    "    p.component_id = $comp_id, "
                    "    p.voltage = $voltage, "
                    "    p.current_max = $current_max",
                    {
                        "pin_id": pin_id,
                        "name": pin_tmpl["name"],
                        "direction": pin_tmpl["direction"],
                        "comp_id": comp_id,
                        "voltage": pin_tmpl["voltage"],
                        "current_max": pin_tmpl["current_max"],
                    },
                )

                # HAS_PIN relationship
                await self._bridge.neo4j_write(
                    "MATCH (c:Component {id: $comp_id}), "
                    "      (p:Pin {id: $pin_id}) "
                    "MERGE (c)-[:HAS_PIN]->(p)",
                    {"comp_id": comp_id, "pin_id": pin_id},
                )
                count += 1

        return count

    async def _create_buses(
        self,
        active_ids: set[str],
    ) -> tuple[int, int]:
        """Create Net nodes and (Pin)-[:CONNECTED_TO]->(Pin) relationships.

        Returns:
            Tuple of (nets_created, connections_created).
        """
        nets_created = 0
        conns_created = 0

        for rule in BUS_RULES:
            # Filter connections to only those whose components are active
            active_conns = [
                conn for conn in rule.connections
                if conn.source_comp in active_ids and conn.dest_comp in active_ids
            ]
            if not active_conns:
                continue

            net_id = f"net_{rule.name}"

            # Create the Net node
            await self._bridge.neo4j_write(
                "MERGE (n:Net {id: $net_id}) "
                "SET n.name = $name, "
                "    n.type = $net_type",
                {
                    "net_id": net_id,
                    "name": rule.name,
                    "net_type": rule.net_type.value,
                },
            )
            nets_created += 1

            # Create connections for each wire in this bus
            for conn in active_conns:
                src_pin_id = f"{conn.source_comp}_{conn.source_pin}"
                dst_pin_id = f"{conn.dest_comp}_{conn.dest_pin}"

                # Pin-to-Pin connection
                await self._bridge.neo4j_write(
                    "MATCH (src:Pin {id: $src_id}), "
                    "      (dst:Pin {id: $dst_id}) "
                    "MERGE (src)-[:CONNECTED_TO {net_id: $net_id}]->(dst)",
                    {
                        "src_id": src_pin_id,
                        "dst_id": dst_pin_id,
                        "net_id": net_id,
                    },
                )

                # Associate pins with the net
                await self._bridge.neo4j_write(
                    "MATCH (n:Net {id: $net_id}), "
                    "      (p:Pin {id: $pin_id}) "
                    "MERGE (n)-[:INCLUDES_PIN]->(p)",
                    {"net_id": net_id, "pin_id": src_pin_id},
                )
                await self._bridge.neo4j_write(
                    "MATCH (n:Net {id: $net_id}), "
                    "      (p:Pin {id: $pin_id}) "
                    "MERGE (n)-[:INCLUDES_PIN]->(p)",
                    {"net_id": net_id, "pin_id": dst_pin_id},
                )
                conns_created += 1

        return nets_created, conns_created

    async def _set_actual_currents(
        self,
        active_ids: set[str],
        comp_lookup: dict[str, dict[str, Any]],
    ) -> None:
        """Compute and set actual_current on VCC/power input pins.

        For each power-consuming component, actual current is derived from:
            I = P / V
        where P is the component's power_w and V is the pin voltage.
        """
        for comp_id in sorted(active_ids):
            comp = comp_lookup.get(comp_id)
            if comp is None:
                continue

            power_w = comp.get("power_w", 0.0)
            if power_w <= 0:
                continue

            voltage = comp.get("voltage", 0.0)
            if voltage <= 0:
                continue

            actual_current = round(power_w / voltage, 6)

            # Find the VCC or main power input pin for this component
            templates = PIN_TEMPLATES.get(comp_id, [])
            power_pin_names = [
                t["name"] for t in templates
                if t["direction"] == "INPUT" and t["voltage"] > 0
            ]

            for pin_name in power_pin_names:
                pin_id = f"{comp_id}_{pin_name}"
                await self._bridge.neo4j_write(
                    "MATCH (p:Pin {id: $pin_id}) "
                    "SET p.actual_current = $current",
                    {"pin_id": pin_id, "current": actual_current},
                )

        logger.debug("Actual currents set for active load components")
