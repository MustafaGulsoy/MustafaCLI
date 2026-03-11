# SAT-MAESTRO Mechanical Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use Claude Teams (TeamCreate) to implement this plan. Each phase maps to a team member. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full mechanical engineering analysis (structural, thermal, mechanism, vibration, cross-discipline) to SAT-MAESTRO via MCP-first architecture, migrating existing electrical agent to MCP.

**Architecture:** Orchestrator pattern — MCP bridge calls external tools (Neo4j, FreeCAD, CalculiX, Gmsh) via MCP protocol. Simple calculations (mass budget, CoG, lumped-parameter thermal) run locally. Complex analysis delegates to MCP servers.

**Tech Stack:** Python 3.11+, MCP SDK (`mcp`), CalculiX (CLI), Gmsh (Python API), FreeCAD MCP (external), Neo4j MCP (official), pyNastran, numpy

**Spec:** `docs/superpowers/specs/2026-03-11-sat-maestro-mechanical-design.md`

---

## File Structure

### New Files

```
src/plugins/sat_maestro/
├── core/
│   └── mcp_bridge.py                    # Central MCP communication layer
│
├── mechanical/
│   ├── __init__.py
│   ├── agent.py                         # MechanicalAgent orchestrator
│   ├── structural/
│   │   ├── __init__.py
│   │   ├── mass_budget.py               # Mass budget analysis
│   │   ├── cog_calculator.py            # Center of gravity calculation
│   │   └── assembly_validator.py        # Assembly tree validation
│   ├── thermal/
│   │   ├── __init__.py
│   │   ├── node_model.py               # Lumped-parameter thermal solver
│   │   ├── thermal_checker.py          # Temperature limit validation
│   │   └── orbital_cycle.py            # Orbital thermal cycle (hot/cold)
│   ├── mechanism/
│   │   ├── __init__.py
│   │   ├── deployment.py               # Deployment sequence validation
│   │   └── kinematic.py                # Kinematic + kinetic analysis
│   ├── vibration/
│   │   ├── __init__.py
│   │   ├── modal.py                    # Modal analysis evaluation
│   │   ├── random_vib.py              # Random vibration (PSD → RMS)
│   │   └── shock.py                    # Shock response spectrum
│   └── rules/
│       ├── __init__.py
│       └── ecss_mechanical.py          # ECSS-E-ST-32/31/33 rules (40+)
│
├── cross_discipline/
│   ├── __init__.py
│   ├── agent.py                        # CrossDisciplineAgent
│   ├── mass_thermal.py                 # Mass ↔ thermal correlation
│   ├── electrical_thermal.py           # Power dissipation → thermal
│   ├── harness_routing.py             # Cable routing validation
│   └── mounting_check.py              # Mounting compatibility
│
└── mcp_servers/
    ├── calculix/
    │   ├── __init__.py
    │   ├── server.py                   # CalculiX MCP server (mcp SDK)
    │   ├── solver.py                   # CalculiX CLI wrapper
    │   └── result_parser.py            # .frd/.dat parser (pyNastran)
    └── gmsh/
        ├── __init__.py
        ├── server.py                   # Gmsh MCP server (mcp SDK)
        └── mesher.py                   # Gmsh Python API wrapper

tests/plugins/sat_maestro/
├── core/
│   └── test_mcp_bridge.py
├── mechanical/
│   ├── test_mass_budget.py
│   ├── test_cog_calculator.py
│   ├── test_assembly_validator.py
│   ├── test_thermal_solver.py
│   ├── test_thermal_checker.py
│   ├── test_orbital_cycle.py
│   ├── test_deployment.py
│   ├── test_kinematic.py
│   ├── test_modal.py
│   ├── test_random_vib.py
│   ├── test_shock.py
│   └── test_mechanical_agent.py
├── cross_discipline/
│   ├── test_mass_thermal.py
│   ├── test_electrical_thermal.py
│   ├── test_harness_routing.py
│   └── test_mounting_check.py
└── mcp_servers/
    ├── test_calculix_server.py
    ├── test_calculix_parser.py
    ├── test_gmsh_server.py
    └── test_gmsh_mesher.py
```

### Modified Files

```
src/plugins/sat_maestro/core/graph_models.py    # Add mechanical dataclasses
src/plugins/sat_maestro/core/report.py          # Add mechanical report sections
src/plugins/sat_maestro/plugin.py               # Add mechanical + cross-discipline tools
src/plugins/sat_maestro/config.py               # Add mechanical config fields
src/plugins/sat_maestro/db/seed_rules.py        # Add mechanical ECSS rules
src/plugins/sat_maestro/electrical/agent.py     # Refactor to use MCP bridge
requirements-sat-maestro.txt                     # Add new dependencies
```

### Removed Files (after migration)

```
src/plugins/sat_maestro/core/neo4j_client.py    # Replaced by neo4j/mcp via mcp_bridge
src/plugins/sat_maestro/core/graph_ops.py       # Replaced by neo4j/mcp via mcp_bridge
```

---

## Chunk 1: Phase 0 — MCP Infrastructure

### Task 1: MCP Bridge Core

**Owner:** integration-eng
**Files:**
- Create: `src/plugins/sat_maestro/core/mcp_bridge.py`
- Test: `tests/plugins/sat_maestro/core/test_mcp_bridge.py`

- [ ] **Step 1: Write failing test for McpBridge initialization**

```python
# tests/plugins/sat_maestro/core/test_mcp_bridge.py
"""Tests for MCP Bridge - central MCP communication layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge, McpServerConfig


class TestMcpBridge:
    """Test MCP Bridge initialization and server management."""

    def test_create_bridge_with_config(self):
        """Bridge accepts server configurations."""
        config = {
            "neo4j": McpServerConfig(name="neo4j", command="npx", args=["-y", "@neo4j/mcp-neo4j"]),
            "freecad": McpServerConfig(name="freecad", command="python", args=["-m", "freecad_mcp"]),
        }
        bridge = McpBridge(servers=config)
        assert "neo4j" in bridge.servers
        assert "freecad" in bridge.servers

    def test_bridge_not_connected_by_default(self):
        bridge = McpBridge(servers={})
        assert not bridge.is_connected("neo4j")

    @pytest.mark.asyncio
    async def test_call_tool_on_disconnected_server_raises(self):
        bridge = McpBridge(servers={})
        with pytest.raises(RuntimeError, match="not connected"):
            await bridge.call_tool("neo4j", "read_neo4j_cypher", {"query": "RETURN 1"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/sat_maestro/core/test_mcp_bridge.py -v --override-ini="addopts="`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.plugins.sat_maestro.core.mcp_bridge'`

- [ ] **Step 3: Implement McpBridge**

```python
# src/plugins/sat_maestro/core/mcp_bridge.py
"""MCP Bridge - central communication layer for all MCP server calls."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


class McpBridge:
    """Central bridge for calling tools on MCP servers.

    All SAT-MAESTRO agents use this bridge to communicate with
    external tools (Neo4j, FreeCAD, CalculiX, Gmsh) via MCP protocol.
    """

    def __init__(self, servers: dict[str, McpServerConfig] | None = None) -> None:
        self._server_configs = servers or {}
        self._clients: dict[str, Any] = {}
        self._sessions: dict[str, Any] = {}

    @property
    def servers(self) -> dict[str, McpServerConfig]:
        return self._server_configs

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected."""
        return server_name in self._sessions

    async def connect(self, server_name: str) -> None:
        """Connect to an MCP server by name."""
        if server_name not in self._server_configs:
            raise ValueError(f"Unknown MCP server: {server_name}")

        config = self._server_configs[server_name]

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env or None,
            )

            client = stdio_client(params)
            read, write = await client.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()

            self._clients[server_name] = client
            self._sessions[server_name] = session
            logger.info("Connected to MCP server: %s", server_name)

        except Exception as e:
            logger.error("Failed to connect to MCP server %s: %s", server_name, e)
            raise

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server."""
        if server_name in self._sessions:
            try:
                await self._sessions[server_name].__aexit__(None, None, None)
                await self._clients[server_name].__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error disconnecting from %s: %s", server_name, e)
            finally:
                del self._sessions[server_name]
                del self._clients[server_name]

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._sessions.keys()):
            await self.disconnect(name)

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on an MCP server and return the result."""
        if server_name not in self._sessions:
            raise RuntimeError(f"MCP server '{server_name}' not connected. Call connect() first.")

        session = self._sessions[server_name]
        result = await session.call_tool(tool_name, arguments or {})

        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown error"
            raise RuntimeError(f"MCP tool '{tool_name}' error: {error_text}")

        # Extract text content from result
        if result.content and hasattr(result.content[0], 'text'):
            import json
            text = result.content[0].text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text

        return result.content

    # -- Convenience methods for common operations --

    async def neo4j_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a Cypher query via Neo4j MCP server."""
        return await self.call_tool("neo4j", "read_neo4j_cypher", {
            "query": cypher,
            "params": params or {},
        })

    async def neo4j_write(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a write Cypher query via Neo4j MCP server."""
        return await self.call_tool("neo4j", "write_neo4j_cypher", {
            "query": cypher,
            "params": params or {},
        })

    async def neo4j_schema(self) -> dict:
        """Get Neo4j database schema."""
        return await self.call_tool("neo4j", "get_neo4j_schema", {})

    async def freecad_execute(self, code: str) -> Any:
        """Execute Python code in FreeCAD context."""
        return await self.call_tool("freecad", "execute_code", {"code": code})

    async def freecad_import_step(self, file_path: str) -> dict:
        """Import a STEP file via FreeCAD MCP."""
        return await self.freecad_execute(
            f"import Part; Part.open('{file_path}'); "
            f"doc = FreeCAD.ActiveDocument; "
            f"[{{'name': o.Label, 'type': o.TypeId}} for o in doc.Objects]"
        )

    async def freecad_mass_properties(self, body_name: str = "") -> dict:
        """Get mass properties (mass, CoG, inertia) from FreeCAD."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument
shapes = [o.Shape for o in doc.Objects if hasattr(o, 'Shape')]
if shapes:
    compound = Part.makeCompound(shapes)
    props = compound.ShapeInfo if hasattr(compound, 'ShapeInfo') else {{}}
    result = {{
        'mass': compound.Mass,
        'volume': compound.Volume,
        'cog': list(compound.CenterOfGravity),
        'inertia': list(compound.MatrixOfInertia),
    }}
else:
    result = {{'error': 'No shapes found'}}
result
"""
        return await self.freecad_execute(code)

    async def gmsh_mesh(self, step_file: str, element_size: float = 5.0,
                         element_type: str = "tet", order: int = 2) -> str:
        """Generate FEM mesh from STEP file via Gmsh MCP."""
        return await self.call_tool("gmsh", "gmsh_mesh_from_step", {
            "step_file": step_file,
            "element_size": element_size,
            "element_type": element_type,
            "order": order,
        })

    async def gmsh_quality(self, mesh_file: str) -> dict:
        """Check mesh quality via Gmsh MCP."""
        return await self.call_tool("gmsh", "gmsh_quality_check", {
            "mesh_file": mesh_file,
        })

    async def calculix_solve(self, input_file: str, solve_type: str = "static") -> dict:
        """Run CalculiX solver via MCP."""
        tool_map = {
            "static": "ccx_solve_static",
            "modal": "ccx_solve_modal",
            "thermal": "ccx_solve_thermal",
            "buckling": "ccx_solve_buckling",
        }
        tool = tool_map.get(solve_type, "ccx_solve_static")
        return await self.call_tool("calculix", tool, {"input_file": input_file})

    async def calculix_results(self, result_file: str, field: str = "stress") -> dict:
        """Read CalculiX results via MCP."""
        return await self.call_tool("calculix", "ccx_read_results", {
            "result_file": result_file,
            "field": field,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/plugins/sat_maestro/core/test_mcp_bridge.py -v --override-ini="addopts="`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/plugins/sat_maestro/core/mcp_bridge.py tests/plugins/sat_maestro/core/test_mcp_bridge.py
git commit -m "feat(sat-maestro): add MCP Bridge communication layer"
```

---

### Task 2: Mechanical Graph Models

**Owner:** integration-eng
**Files:**
- Modify: `src/plugins/sat_maestro/core/graph_models.py`
- Test: `tests/plugins/sat_maestro/core/test_graph_models.py` (extend)

- [ ] **Step 1: Write failing tests for new mechanical models**

```python
# Add to tests/plugins/sat_maestro/core/test_graph_models.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/plugins/sat_maestro/core/test_graph_models.py::TestMechanicalModels -v --override-ini="addopts="`
Expected: FAIL — ImportError

- [ ] **Step 3: Add mechanical dataclasses to graph_models.py**

Add the following after the existing `Trace` dataclass in `src/plugins/sat_maestro/core/graph_models.py`:

```python
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
    density: float  # kg/m³
    youngs_modulus: float = 0.0  # Pa
    poisson: float = 0.0
    thermal_conductivity: float = 0.0  # W/(m·K)
    cte: float = 0.0  # coefficient of thermal expansion, 1/K
    yield_strength: float = 0.0  # Pa
    ultimate_strength: float = 0.0  # Pa
    specific_heat: float = 0.0  # J/(kg·K)


@dataclass
class Structure:
    """Structural element (panel, bracket, beam)."""
    id: str
    name: str
    material: str  # material id or name
    mass: float  # kg
    volume: float = 0.0  # m³
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
    temperature: float = 20.0  # °C
    capacity: float = 0.0  # J/K (thermal mass)
    power_dissipation: float = 0.0  # W
    op_min_temp: float = -40.0  # °C operational min
    op_max_temp: float = 85.0  # °C operational max


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
    torque: float = 0.0  # N·m (available torque)
    friction_torque: float = 0.0  # N·m
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
    psd_profile: list[tuple[float, float]] = field(default_factory=list)  # (Hz, g²/Hz)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/plugins/sat_maestro/core/test_graph_models.py -v --override-ini="addopts="`
Expected: ALL PASSED (old + new)

- [ ] **Step 5: Commit**

```bash
git add src/plugins/sat_maestro/core/graph_models.py tests/plugins/sat_maestro/core/test_graph_models.py
git commit -m "feat(sat-maestro): add mechanical graph models (Structure, Assembly, ThermalNode, etc.)"
```

---

### Task 3: mcp-gmsh Server

**Owner:** mcp-engineer
**Files:**
- Create: `src/plugins/sat_maestro/mcp_servers/gmsh/__init__.py`
- Create: `src/plugins/sat_maestro/mcp_servers/gmsh/mesher.py`
- Create: `src/plugins/sat_maestro/mcp_servers/gmsh/server.py`
- Create: `src/plugins/sat_maestro/mcp_servers/__init__.py`
- Test: `tests/plugins/sat_maestro/mcp_servers/test_gmsh_mesher.py`
- Test: `tests/plugins/sat_maestro/mcp_servers/test_gmsh_server.py`

- [ ] **Step 1: Write failing test for Gmsh mesher wrapper**

```python
# tests/plugins/sat_maestro/mcp_servers/test_gmsh_mesher.py
"""Tests for Gmsh mesher wrapper."""
import pytest
from unittest.mock import patch, MagicMock

from src.plugins.sat_maestro.mcp_servers.gmsh.mesher import GmshMesher


class TestGmshMesher:

    def test_mesher_init(self):
        mesher = GmshMesher()
        assert mesher is not None

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_mesh_from_step(self, mock_gmsh):
        """Mesher calls gmsh API to generate mesh from STEP."""
        mesher = GmshMesher()
        result = mesher.mesh_from_step("test.step", element_size=5.0)
        mock_gmsh.initialize.assert_called_once()
        mock_gmsh.open.assert_called_once_with("test.step")
        assert "mesh_file" in result

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_mesh_quality_check(self, mock_gmsh):
        """Mesher returns quality metrics."""
        mock_gmsh.model.mesh.getElementQualities.return_value = [0.8, 0.9, 0.7]
        mesher = GmshMesher()
        result = mesher.quality_check("test.msh")
        assert "min_quality" in result
        assert "avg_quality" in result

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_mesh_info(self, mock_gmsh):
        """Mesher returns mesh statistics."""
        mock_gmsh.model.mesh.getNodes.return_value = ([1,2,3], [0]*9, [])
        mock_gmsh.model.mesh.getElements.return_value = ([4], [[1,2]], [[1,2,3,4,5,6,7,8]])
        mesher = GmshMesher()
        result = mesher.info("test.msh")
        assert "node_count" in result

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_convert_format(self, mock_gmsh):
        """Mesher converts mesh to different format."""
        mesher = GmshMesher()
        result = mesher.convert("test.msh", "inp")
        mock_gmsh.write.assert_called()
        assert result.endswith(".inp")
```

- [ ] **Step 2: Implement GmshMesher**

```python
# src/plugins/sat_maestro/mcp_servers/gmsh/mesher.py
"""Gmsh Python API wrapper for mesh generation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import gmsh
except ImportError:
    gmsh = None


class GmshMesher:
    """Wrapper around Gmsh Python API for mesh generation and manipulation."""

    def mesh_from_step(self, step_file: str, element_size: float = 5.0,
                       element_type: str = "tet", order: int = 2) -> dict[str, Any]:
        """Generate FEM mesh from STEP file."""
        if gmsh is None:
            raise ImportError("gmsh package required. Install with: pip install gmsh")

        gmsh.initialize()
        try:
            gmsh.open(step_file)
            gmsh.option.setNumber("Mesh.MeshSizeMax", element_size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", element_size * 0.1)
            gmsh.option.setNumber("Mesh.ElementOrder", order)

            if element_type == "hex":
                gmsh.option.setNumber("Mesh.Algorithm3D", 9)  # hex-dominant
            else:
                gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay tet

            gmsh.model.mesh.generate(3)

            out_path = str(Path(step_file).with_suffix(".msh"))
            gmsh.write(out_path)

            nodes, _, _ = gmsh.model.mesh.getNodes()
            elem_types, _, _ = gmsh.model.mesh.getElements()

            return {
                "mesh_file": out_path,
                "node_count": len(nodes),
                "element_types": len(elem_types),
                "element_size": element_size,
                "order": order,
            }
        finally:
            gmsh.finalize()

    def mesh_from_geo(self, geo_file: str, element_size: float = 5.0) -> dict[str, Any]:
        """Generate mesh from .geo script."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(geo_file)
            gmsh.option.setNumber("Mesh.MeshSizeMax", element_size)
            gmsh.model.mesh.generate(3)

            out_path = str(Path(geo_file).with_suffix(".msh"))
            gmsh.write(out_path)

            nodes, _, _ = gmsh.model.mesh.getNodes()
            return {"mesh_file": out_path, "node_count": len(nodes)}
        finally:
            gmsh.finalize()

    def quality_check(self, mesh_file: str, metric: str = "gamma") -> dict[str, Any]:
        """Check mesh quality."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            qualities = gmsh.model.mesh.getElementQualities(qualityType=metric)
            return {
                "min_quality": min(qualities) if qualities else 0.0,
                "max_quality": max(qualities) if qualities else 0.0,
                "avg_quality": sum(qualities) / len(qualities) if qualities else 0.0,
                "elements_below_03": sum(1 for q in qualities if q < 0.3),
                "total_elements": len(qualities),
            }
        finally:
            gmsh.finalize()

    def info(self, mesh_file: str) -> dict[str, Any]:
        """Get mesh statistics."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            nodes, _, _ = gmsh.model.mesh.getNodes()
            elem_types, elem_tags, _ = gmsh.model.mesh.getElements()
            total_elems = sum(len(t) for t in elem_tags)
            return {
                "node_count": len(nodes),
                "element_count": total_elems,
                "element_types": len(elem_types),
            }
        finally:
            gmsh.finalize()

    def convert(self, mesh_file: str, output_format: str = "inp") -> str:
        """Convert mesh to different format."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            out_path = str(Path(mesh_file).with_suffix(f".{output_format}"))
            gmsh.write(out_path)
            return out_path
        finally:
            gmsh.finalize()

    def refine_region(self, mesh_file: str, box: dict, target_size: float) -> str:
        """Refine mesh in a box region."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            field = gmsh.model.mesh.field.add("Box")
            gmsh.model.mesh.field.setNumber(field, "VIn", target_size)
            gmsh.model.mesh.field.setNumber(field, "VOut", target_size * 5)
            gmsh.model.mesh.field.setNumber(field, "XMin", box.get("x_min", 0))
            gmsh.model.mesh.field.setNumber(field, "XMax", box.get("x_max", 1))
            gmsh.model.mesh.field.setNumber(field, "YMin", box.get("y_min", 0))
            gmsh.model.mesh.field.setNumber(field, "YMax", box.get("y_max", 1))
            gmsh.model.mesh.field.setNumber(field, "ZMin", box.get("z_min", 0))
            gmsh.model.mesh.field.setNumber(field, "ZMax", box.get("z_max", 1))
            gmsh.model.mesh.field.setAsBackgroundMesh(field)
            gmsh.model.mesh.generate(3)

            out_path = str(Path(mesh_file).with_suffix(".refined.msh"))
            gmsh.write(out_path)
            return out_path
        finally:
            gmsh.finalize()
```

- [ ] **Step 3: Implement Gmsh MCP server**

```python
# src/plugins/sat_maestro/mcp_servers/gmsh/server.py
"""Gmsh MCP Server - mesh generation via Model Context Protocol."""
from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .mesher import GmshMesher

logger = logging.getLogger(__name__)

app = Server("mcp-gmsh")
mesher = GmshMesher()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="gmsh_mesh_from_step", description="Generate FEM mesh from STEP file",
             inputSchema={"type": "object", "properties": {
                 "step_file": {"type": "string"}, "element_size": {"type": "number", "default": 5.0},
                 "element_type": {"type": "string", "default": "tet"},
                 "order": {"type": "integer", "default": 2},
             }, "required": ["step_file"]}),
        Tool(name="gmsh_mesh_from_geo", description="Generate mesh from .geo script",
             inputSchema={"type": "object", "properties": {
                 "geo_file": {"type": "string"}, "element_size": {"type": "number", "default": 5.0},
             }, "required": ["geo_file"]}),
        Tool(name="gmsh_quality_check", description="Check mesh quality",
             inputSchema={"type": "object", "properties": {
                 "mesh_file": {"type": "string"}, "metric": {"type": "string", "default": "gamma"},
             }, "required": ["mesh_file"]}),
        Tool(name="gmsh_info", description="Get mesh statistics",
             inputSchema={"type": "object", "properties": {
                 "mesh_file": {"type": "string"},
             }, "required": ["mesh_file"]}),
        Tool(name="gmsh_convert", description="Convert mesh format",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "output_format": {"type": "string", "default": "inp"},
             }, "required": ["input_file"]}),
        Tool(name="gmsh_refine_region", description="Refine mesh in a box region",
             inputSchema={"type": "object", "properties": {
                 "mesh_file": {"type": "string"},
                 "region_box": {"type": "object"}, "target_size": {"type": "number"},
             }, "required": ["mesh_file", "region_box", "target_size"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "gmsh_mesh_from_step":
            result = mesher.mesh_from_step(**arguments)
        elif name == "gmsh_mesh_from_geo":
            result = mesher.mesh_from_geo(**arguments)
        elif name == "gmsh_quality_check":
            result = mesher.quality_check(**arguments)
        elif name == "gmsh_info":
            result = mesher.info(**arguments)
        elif name == "gmsh_convert":
            result = mesher.convert(arguments["input_file"], arguments.get("output_format", "inp"))
        elif name == "gmsh_refine_region":
            result = mesher.refine_region(arguments["mesh_file"],
                                          arguments["region_box"], arguments["target_size"])
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 4: Create __init__.py files**

```python
# src/plugins/sat_maestro/mcp_servers/__init__.py
"""SAT-MAESTRO MCP Servers."""

# src/plugins/sat_maestro/mcp_servers/gmsh/__init__.py
"""Gmsh MCP Server for mesh generation."""
```

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/plugins/sat_maestro/mcp_servers/test_gmsh_mesher.py -v --override-ini="addopts="`
Expected: ALL PASSED

```bash
git add src/plugins/sat_maestro/mcp_servers/ tests/plugins/sat_maestro/mcp_servers/
git commit -m "feat(sat-maestro): add mcp-gmsh server for mesh generation"
```

---

### Task 4: mcp-calculix Server

**Owner:** mcp-engineer
**Files:**
- Create: `src/plugins/sat_maestro/mcp_servers/calculix/__init__.py`
- Create: `src/plugins/sat_maestro/mcp_servers/calculix/solver.py`
- Create: `src/plugins/sat_maestro/mcp_servers/calculix/result_parser.py`
- Create: `src/plugins/sat_maestro/mcp_servers/calculix/server.py`
- Test: `tests/plugins/sat_maestro/mcp_servers/test_calculix_parser.py`
- Test: `tests/plugins/sat_maestro/mcp_servers/test_calculix_server.py`

- [ ] **Step 1: Write failing test for CalculiX result parser**

```python
# tests/plugins/sat_maestro/mcp_servers/test_calculix_parser.py
"""Tests for CalculiX result parser."""
import pytest
from unittest.mock import patch, MagicMock

from src.plugins.sat_maestro.mcp_servers.calculix.result_parser import CalculixResultParser


class TestCalculixResultParser:

    def test_parser_init(self):
        parser = CalculixResultParser()
        assert parser is not None

    def test_parse_dat_frequencies(self):
        """Parser extracts modal frequencies from .dat file."""
        dat_content = """
     E I G E N V A L U E   O U T P U T

     MODE NO   EIGENVALUE                      FREQUENCY
                                          (RAD/TIME)      (CYCLES/TIME)

          1   4.8900E+04                 2.2114E+02       3.5200E+01
          2   9.3600E+04                 3.0594E+02       4.8700E+01
          3   1.5240E+05                 3.9038E+02       6.2100E+01
"""
        parser = CalculixResultParser()
        result = parser.parse_dat_frequencies(dat_content)
        assert len(result) == 3
        assert abs(result[0]["frequency_hz"] - 35.2) < 0.1
        assert abs(result[1]["frequency_hz"] - 48.7) < 0.1

    def test_parse_dat_stress(self):
        """Parser extracts stress values from .dat file."""
        dat_content = """
     S T R E S S E S   F O R   S O L I D   E L E M E N T S

     ELEMENT  NODE    SXX         SYY         SZZ         SXY         SXZ         SYZ
         1      1  1.234E+06  2.345E+06  3.456E+06  4.567E+05  5.678E+05  6.789E+05
         1      2  2.234E+06  3.345E+06  4.456E+06  5.567E+05  6.678E+05  7.789E+05
"""
        parser = CalculixResultParser()
        result = parser.parse_dat_stress(dat_content)
        assert result["max_von_mises"] > 0
        assert "elements" in result

    def test_parse_empty_dat(self):
        """Parser handles empty/missing data gracefully."""
        parser = CalculixResultParser()
        result = parser.parse_dat_frequencies("")
        assert result == []
```

- [ ] **Step 2: Implement CalculixResultParser**

```python
# src/plugins/sat_maestro/mcp_servers/calculix/result_parser.py
"""CalculiX result file parser (.dat/.frd)."""
from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)


class CalculixResultParser:
    """Parse CalculiX output files (.dat and .frd)."""

    def parse_dat_frequencies(self, content: str) -> list[dict[str, Any]]:
        """Extract modal frequencies from .dat eigenvalue output."""
        frequencies = []
        pattern = r'\s+(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)'

        in_eigen_section = False
        for line in content.split("\n"):
            if "EIGENVALUE" in line and "OUTPUT" in line:
                in_eigen_section = True
                continue
            if in_eigen_section:
                match = re.match(pattern, line.strip())
                if match:
                    mode = int(match.group(1))
                    eigenvalue = float(match.group(2))
                    freq_hz = float(match.group(4))
                    frequencies.append({
                        "mode": mode,
                        "eigenvalue": eigenvalue,
                        "frequency_hz": freq_hz,
                    })

        return frequencies

    def parse_dat_stress(self, content: str) -> dict[str, Any]:
        """Extract stress values from .dat stress output."""
        elements = []
        max_von_mises = 0.0

        pattern = r'\s+(\d+)\s+(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)'

        for line in content.split("\n"):
            match = re.match(pattern, line.strip())
            if match:
                sxx = float(match.group(3))
                syy = float(match.group(4))
                szz = float(match.group(5))
                sxy = float(match.group(6))
                sxz = float(match.group(7))
                syz = float(match.group(8))

                von_mises = math.sqrt(0.5 * (
                    (sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2
                    + 6 * (sxy**2 + sxz**2 + syz**2)
                ))

                max_von_mises = max(max_von_mises, von_mises)
                elements.append({
                    "element": int(match.group(1)),
                    "node": int(match.group(2)),
                    "von_mises": von_mises,
                })

        return {"max_von_mises": max_von_mises, "elements": elements}

    def parse_dat_displacement(self, content: str) -> dict[str, Any]:
        """Extract displacement values from .dat output."""
        max_disp = 0.0
        nodes = []

        pattern = r'\s+(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)'

        in_disp_section = False
        for line in content.split("\n"):
            if "DISPLACEMENTS" in line:
                in_disp_section = True
                continue
            if in_disp_section:
                match = re.match(pattern, line.strip())
                if match:
                    dx = float(match.group(2))
                    dy = float(match.group(3))
                    dz = float(match.group(4))
                    mag = math.sqrt(dx**2 + dy**2 + dz**2)
                    max_disp = max(max_disp, mag)
                    nodes.append({
                        "node": int(match.group(1)),
                        "displacement": mag,
                    })

        return {"max_displacement": max_disp, "nodes": nodes}
```

- [ ] **Step 3: Implement CalculiX CLI wrapper**

```python
# src/plugins/sat_maestro/mcp_servers/calculix/solver.py
"""CalculiX CLI wrapper for running FEM analyses."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from .result_parser import CalculixResultParser

logger = logging.getLogger(__name__)


class CalculixSolver:
    """Wrapper around CalculiX (ccx) command-line solver."""

    def __init__(self, ccx_path: str | None = None) -> None:
        self._ccx = ccx_path or shutil.which("ccx") or "ccx"
        self._parser = CalculixResultParser()

    async def solve(self, input_file: str, num_cpus: int = 1) -> dict[str, Any]:
        """Run CalculiX solver on input file."""
        inp_path = Path(input_file)
        if not inp_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        job_name = inp_path.stem
        work_dir = inp_path.parent

        env = {"OMP_NUM_THREADS": str(num_cpus)}
        cmd = [self._ccx, "-i", job_name]

        logger.info("Running CalculiX: %s in %s", " ".join(cmd), work_dir)

        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(work_dir), env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"CalculiX failed (exit {proc.returncode}): {stderr.decode()}"
            )

        # Collect output files
        dat_file = work_dir / f"{job_name}.dat"
        frd_file = work_dir / f"{job_name}.frd"

        result = {
            "job_name": job_name,
            "return_code": proc.returncode,
            "dat_file": str(dat_file) if dat_file.exists() else None,
            "frd_file": str(frd_file) if frd_file.exists() else None,
        }

        # Auto-parse results if available
        if dat_file.exists():
            dat_content = dat_file.read_text(encoding="utf-8", errors="replace")
            freqs = self._parser.parse_dat_frequencies(dat_content)
            if freqs:
                result["frequencies"] = freqs
            stress = self._parser.parse_dat_stress(dat_content)
            if stress["elements"]:
                result["max_von_mises"] = stress["max_von_mises"]
            disp = self._parser.parse_dat_displacement(dat_content)
            if disp["nodes"]:
                result["max_displacement"] = disp["max_displacement"]

        return result

    async def check_input(self, input_file: str) -> dict[str, Any]:
        """Validate CalculiX input file syntax."""
        inp_path = Path(input_file)
        if not inp_path.exists():
            return {"valid": False, "error": f"File not found: {input_file}"}

        content = inp_path.read_text(encoding="utf-8", errors="replace")
        issues = []

        required_keywords = ["*NODE", "*ELEMENT"]
        for kw in required_keywords:
            if kw not in content.upper():
                issues.append(f"Missing keyword: {kw}")

        if "*STEP" not in content.upper():
            issues.append("Missing *STEP definition")

        if "*END STEP" not in content.upper():
            issues.append("Missing *END STEP")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "line_count": len(content.split("\n")),
        }

    def get_version(self) -> str:
        """Get CalculiX version string."""
        import subprocess
        try:
            result = subprocess.run(
                [self._ccx, "-v"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or result.stderr.strip()
        except FileNotFoundError:
            return "CalculiX not found"
        except Exception as e:
            return f"Error: {e}"
```

- [ ] **Step 4: Implement CalculiX MCP server**

```python
# src/plugins/sat_maestro/mcp_servers/calculix/server.py
"""CalculiX MCP Server - FEM solver via Model Context Protocol."""
from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .solver import CalculixSolver

logger = logging.getLogger(__name__)

app = Server("mcp-calculix")
solver = CalculixSolver()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="ccx_solve_static", description="Run static structural analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "num_cpus": {"type": "integer", "default": 1},
             }, "required": ["input_file"]}),
        Tool(name="ccx_solve_modal", description="Run modal (frequency) analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "num_modes": {"type": "integer", "default": 20},
             }, "required": ["input_file"]}),
        Tool(name="ccx_solve_thermal", description="Run thermal analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"},
             }, "required": ["input_file"]}),
        Tool(name="ccx_solve_buckling", description="Run buckling analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "num_modes": {"type": "integer", "default": 5},
             }, "required": ["input_file"]}),
        Tool(name="ccx_read_results", description="Read FEM result file",
             inputSchema={"type": "object", "properties": {
                 "result_file": {"type": "string"}, "field": {"type": "string", "default": "stress"},
             }, "required": ["result_file"]}),
        Tool(name="ccx_check_input", description="Validate CalculiX input file",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"},
             }, "required": ["input_file"]}),
        Tool(name="ccx_get_version", description="Get CalculiX version",
             inputSchema={"type": "object", "properties": {}}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name in ("ccx_solve_static", "ccx_solve_modal", "ccx_solve_thermal", "ccx_solve_buckling"):
            result = await solver.solve(arguments["input_file"], arguments.get("num_cpus", 1))
        elif name == "ccx_read_results":
            from pathlib import Path
            from .result_parser import CalculixResultParser
            parser = CalculixResultParser()
            content = Path(arguments["result_file"]).read_text(encoding="utf-8", errors="replace")
            field = arguments.get("field", "stress")
            if field == "stress":
                result = parser.parse_dat_stress(content)
            elif field == "displacement":
                result = parser.parse_dat_displacement(content)
            elif field == "frequency":
                result = parser.parse_dat_frequencies(content)
            else:
                result = {"error": f"Unknown field: {field}"}
        elif name == "ccx_check_input":
            result = await solver.check_input(arguments["input_file"])
        elif name == "ccx_get_version":
            result = {"version": solver.get_version()}
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 5: Create init, run tests, commit**

```python
# src/plugins/sat_maestro/mcp_servers/calculix/__init__.py
"""CalculiX MCP Server for FEM analysis."""
```

Run: `python -m pytest tests/plugins/sat_maestro/mcp_servers/ -v --override-ini="addopts="`

```bash
git add src/plugins/sat_maestro/mcp_servers/calculix/ tests/plugins/sat_maestro/mcp_servers/test_calculix_*.py
git commit -m "feat(sat-maestro): add mcp-calculix server for FEM analysis"
```

---

## Chunk 2: Phase 1 — Structural Module

### Task 5: Mass Budget Analyzer

**Owner:** structural-eng
**Files:**
- Create: `src/plugins/sat_maestro/mechanical/__init__.py`
- Create: `src/plugins/sat_maestro/mechanical/structural/__init__.py`
- Create: `src/plugins/sat_maestro/mechanical/structural/mass_budget.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_mass_budget.py`

- [ ] **Step 1: Write failing test**

```python
# tests/plugins/sat_maestro/mechanical/test_mass_budget.py
"""Tests for mass budget analyzer."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.structural.mass_budget import MassBudgetAnalyzer
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity


class TestMassBudgetAnalyzer:

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        return bridge

    @pytest.fixture
    def analyzer(self, mock_bridge):
        return MassBudgetAnalyzer(mock_bridge, mass_margin=0.10)

    @pytest.mark.asyncio
    async def test_healthy_mass_budget(self, analyzer, mock_bridge):
        """No violations when mass within budget."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 8.0},
            {"name": "AOCS", "total_mass": 5.0},
            {"name": "COMMS", "total_mass": 3.0},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0
        assert result.summary["total_mass"] == 16.0
        assert result.summary["margin"] > 0.10

    @pytest.mark.asyncio
    async def test_over_budget_violation(self, analyzer, mock_bridge):
        """ERROR when total mass exceeds budget."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 15.0},
            {"name": "AOCS", "total_mass": 10.0},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR for v in result.violations)

    @pytest.mark.asyncio
    async def test_low_margin_warning(self, analyzer, mock_bridge):
        """WARNING when margin below threshold."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 17.5},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert result.status == AnalysisStatus.WARN
        assert any(v.severity == Severity.WARNING for v in result.violations)

    @pytest.mark.asyncio
    async def test_subsystem_breakdown(self, analyzer, mock_bridge):
        """Summary includes per-subsystem breakdown."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 5.0},
            {"name": "AOCS", "total_mass": 3.0},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert "subsystems" in result.summary
        assert len(result.summary["subsystems"]) == 2

    @pytest.mark.asyncio
    async def test_empty_graph(self, analyzer, mock_bridge):
        """Handles empty graph gracefully."""
        mock_bridge.neo4j_query.return_value = []
        result = await analyzer.analyze(budget=20.0)
        assert result.summary["total_mass"] == 0.0
```

- [ ] **Step 2: Implement MassBudgetAnalyzer**

```python
# src/plugins/sat_maestro/mechanical/structural/mass_budget.py
"""Mass budget analysis for satellite structures."""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class MassBudgetAnalyzer:
    """Analyzes spacecraft mass budget against allocation with ECSS margins."""

    def __init__(self, bridge: McpBridge, mass_margin: float = 0.10) -> None:
        self._bridge = bridge
        self._margin_threshold = mass_margin

    async def analyze(self, budget: float, subsystem: str | None = None) -> AnalysisResult:
        """Run mass budget analysis.

        Args:
            budget: Total mass budget in kg.
            subsystem: Optional subsystem filter.
        """
        violations: list[Violation] = []

        # Query assemblies from Neo4j
        query = "MATCH (a:Assembly) RETURN a.name AS name, a.total_mass AS total_mass"
        if subsystem:
            query = f"MATCH (a:Assembly {{name: '{subsystem}'}}) RETURN a.name AS name, a.total_mass AS total_mass"

        records = await self._bridge.neo4j_query(query)

        subsystems = []
        total_mass = 0.0
        for r in records:
            mass = r.get("total_mass", 0.0) or 0.0
            total_mass += mass
            subsystems.append({"name": r["name"], "mass": mass})

        margin = (budget - total_mass) / budget if budget > 0 else 1.0

        # Check violations
        if total_mass > budget:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MASS-001",
                severity=Severity.ERROR,
                message=f"Total mass {total_mass:.1f} kg exceeds budget {budget:.1f} kg",
                component_path="spacecraft",
                details={"total_mass": total_mass, "budget": budget},
            ))
        elif margin < self._margin_threshold:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MASS-002",
                severity=Severity.WARNING,
                message=f"Mass margin {margin:.1%} below threshold {self._margin_threshold:.0%}",
                component_path="spacecraft",
                details={"margin": margin, "threshold": self._margin_threshold},
            ))

        status = AnalysisStatus.FAIL if any(v.severity == Severity.ERROR for v in violations) \
            else AnalysisStatus.WARN if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="mass_budget",
            status=status,
            violations=violations,
            summary={
                "total_mass": total_mass,
                "budget": budget,
                "margin": margin,
                "subsystems": subsystems,
            },
        )
```

- [ ] **Step 3: Create __init__.py files, run tests, commit**

```python
# src/plugins/sat_maestro/mechanical/__init__.py
"""SAT-MAESTRO Mechanical Engineering Module."""

# src/plugins/sat_maestro/mechanical/structural/__init__.py
"""Structural analysis sub-module."""
```

Run: `python -m pytest tests/plugins/sat_maestro/mechanical/test_mass_budget.py -v --override-ini="addopts="`

```bash
git add src/plugins/sat_maestro/mechanical/ tests/plugins/sat_maestro/mechanical/
git commit -m "feat(sat-maestro): add mass budget analyzer"
```

---

### Task 6: Center of Gravity Calculator

**Owner:** structural-eng
**Files:**
- Create: `src/plugins/sat_maestro/mechanical/structural/cog_calculator.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_cog_calculator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/plugins/sat_maestro/mechanical/test_cog_calculator.py
"""Tests for center of gravity calculator."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.structural.cog_calculator import CogCalculator
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus


class TestCogCalculator:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def calc(self, mock_bridge):
        return CogCalculator(mock_bridge)

    @pytest.mark.asyncio
    async def test_simple_cog(self, calc, mock_bridge):
        """CoG of two equal masses at symmetric positions."""
        mock_bridge.neo4j_query.return_value = [
            {"mass": 10.0, "cog_x": 0.0, "cog_y": 0.0, "cog_z": 1.0},
            {"mass": 10.0, "cog_x": 0.0, "cog_y": 0.0, "cog_z": -1.0},
        ]
        result = await calc.calculate()
        assert abs(result.summary["cog_x"]) < 0.001
        assert abs(result.summary["cog_z"]) < 0.001  # symmetric → z=0

    @pytest.mark.asyncio
    async def test_weighted_cog(self, calc, mock_bridge):
        """CoG weighted by mass."""
        mock_bridge.neo4j_query.return_value = [
            {"mass": 30.0, "cog_x": 0.0, "cog_y": 0.0, "cog_z": 0.0},
            {"mass": 10.0, "cog_x": 4.0, "cog_y": 0.0, "cog_z": 0.0},
        ]
        result = await calc.calculate()
        assert abs(result.summary["cog_x"] - 1.0) < 0.001  # (30*0+10*4)/40=1.0

    @pytest.mark.asyncio
    async def test_cog_offset_violation(self, calc, mock_bridge):
        """Violation when CoG offset exceeds limit."""
        mock_bridge.neo4j_query.return_value = [
            {"mass": 10.0, "cog_x": 10.0, "cog_y": 0.0, "cog_z": 0.0},
        ]
        result = await calc.calculate(max_offset=5.0)
        assert result.status == AnalysisStatus.FAIL

    @pytest.mark.asyncio
    async def test_empty_graph(self, calc, mock_bridge):
        """Handles no structures gracefully."""
        mock_bridge.neo4j_query.return_value = []
        result = await calc.calculate()
        assert result.summary["total_mass"] == 0.0
```

- [ ] **Step 2: Implement CogCalculator**

```python
# src/plugins/sat_maestro/mechanical/structural/cog_calculator.py
"""Center of gravity calculation for satellite assemblies."""
from __future__ import annotations

import math
import logging
from typing import Any, TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class CogCalculator:
    """Calculate spacecraft center of gravity from structure masses and positions."""

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def calculate(self, subsystem: str | None = None,
                        max_offset: float | None = None) -> AnalysisResult:
        """Calculate CoG and check against offset limits."""
        violations: list[Violation] = []

        query = """
        MATCH (s:Structure)
        RETURN s.mass AS mass, s.cog_x AS cog_x, s.cog_y AS cog_y, s.cog_z AS cog_z
        """
        if subsystem:
            query = f"""
            MATCH (s:Structure {{subsystem: '{subsystem}'}})
            RETURN s.mass AS mass, s.cog_x AS cog_x, s.cog_y AS cog_y, s.cog_z AS cog_z
            """

        records = await self._bridge.neo4j_query(query)

        total_mass = 0.0
        mx = my = mz = 0.0

        for r in records:
            m = r.get("mass", 0.0) or 0.0
            total_mass += m
            mx += m * (r.get("cog_x", 0.0) or 0.0)
            my += m * (r.get("cog_y", 0.0) or 0.0)
            mz += m * (r.get("cog_z", 0.0) or 0.0)

        if total_mass > 0:
            cog_x = mx / total_mass
            cog_y = my / total_mass
            cog_z = mz / total_mass
        else:
            cog_x = cog_y = cog_z = 0.0

        offset = math.sqrt(cog_x**2 + cog_y**2 + cog_z**2)

        if max_offset is not None and offset > max_offset:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-COG-001",
                severity=Severity.ERROR,
                message=f"CoG offset {offset:.3f} m exceeds limit {max_offset:.3f} m",
                component_path="spacecraft",
                details={"offset": offset, "limit": max_offset},
            ))

        status = AnalysisStatus.FAIL if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="cog_analysis",
            status=status,
            violations=violations,
            summary={
                "cog_x": cog_x, "cog_y": cog_y, "cog_z": cog_z,
                "offset": offset, "total_mass": total_mass,
            },
        )
```

- [ ] **Step 3: Run tests and commit**

```bash
git add src/plugins/sat_maestro/mechanical/structural/cog_calculator.py tests/plugins/sat_maestro/mechanical/test_cog_calculator.py
git commit -m "feat(sat-maestro): add center of gravity calculator"
```

---

### Task 7: Assembly Validator

**Owner:** structural-eng
**Files:**
- Create: `src/plugins/sat_maestro/mechanical/structural/assembly_validator.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_assembly_validator.py`

Follow same pattern as Tasks 5-6. Validates:
- Assembly hierarchy consistency (no cycles)
- All structures belong to an assembly
- Material references are valid
- Mass roll-up consistency (assembly mass = sum of child masses)

- [ ] **Step 1-5:** TDD cycle (test → fail → implement → pass → commit)

```bash
git commit -m "feat(sat-maestro): add assembly tree validator"
```

---

## Chunk 3: Phase 2 — Thermal + Mechanism Modules (Parallel)

### Task 8: Thermal Node Model (Simple Solver)

**Owner:** thermal-eng
**Files:**
- Create: `src/plugins/sat_maestro/mechanical/thermal/__init__.py`
- Create: `src/plugins/sat_maestro/mechanical/thermal/node_model.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_thermal_solver.py`

Implements a lumped-parameter thermal solver using numpy matrix solve:
- Build conductance matrix from ThermalNode/ThermalConductance graph
- Solve `[G]{T} = {Q}` for steady-state temperatures
- Support transient solve with time-stepping for orbital cycles
- Store results back to Neo4j via MCP bridge

- [ ] **Step 1-5:** TDD cycle

### Task 9: Thermal Checker

**Owner:** thermal-eng
- Create: `src/plugins/sat_maestro/mechanical/thermal/thermal_checker.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_thermal_checker.py`

Validates temperatures against operational limits per ECSS-E-ST-31C.

### Task 10: Orbital Thermal Cycle

**Owner:** thermal-eng
- Create: `src/plugins/sat_maestro/mechanical/thermal/orbital_cycle.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_orbital_cycle.py`

Models hot/cold orbital cases with eclipse transitions.

### Task 11: Deployment Validator

**Owner:** mechanism-eng (parallel with thermal)
- Create: `src/plugins/sat_maestro/mechanical/mechanism/__init__.py`
- Create: `src/plugins/sat_maestro/mechanical/mechanism/deployment.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_deployment.py`

Validates deployment sequence, angular limits, and latch positions.

### Task 12: Kinematic + Kinetic Analyzer

**Owner:** mechanism-eng
- Create: `src/plugins/sat_maestro/mechanical/mechanism/kinematic.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_kinematic.py`

Torque margin, friction analysis, deployment time estimation per ECSS-E-ST-33C.

---

## Chunk 4: Phase 3 — Vibration Module

### Task 13: Modal Analysis Evaluator

**Owner:** mechanism-eng
- Create: `src/plugins/sat_maestro/mechanical/vibration/__init__.py`
- Create: `src/plugins/sat_maestro/mechanical/vibration/modal.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_modal.py`

Evaluates CalculiX modal analysis results against ECSS frequency requirements.

### Task 14: Random Vibration Analyzer

**Owner:** mechanism-eng
- Create: `src/plugins/sat_maestro/mechanical/vibration/random_vib.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_random_vib.py`

PSD input → gRMS calculation, Miles' equation for SDOF response.

### Task 15: Shock Analysis

**Owner:** mechanism-eng
- Create: `src/plugins/sat_maestro/mechanical/vibration/shock.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_shock.py`

SRS comparison against qualification levels.

---

## Chunk 5: Phase 4 — Cross-Discipline + Integration

### Task 16: Cross-Discipline Agent

**Owner:** integration-eng
- Create: `src/plugins/sat_maestro/cross_discipline/`
- Test: `tests/plugins/sat_maestro/cross_discipline/`

Four analyzers:
- `mass_thermal.py` — Heavy components that are also hot
- `electrical_thermal.py` — Power dissipation → thermal node mapping
- `harness_routing.py` — Cable mass/length/routing validation
- `mounting_check.py` — Component mounting point compatibility

### Task 17: ECSS Mechanical Rules Seed

**Owner:** integration-eng
- Modify: `src/plugins/sat_maestro/db/seed_rules.py`

Add 40+ mechanical ECSS rules (ECSS-E-ST-32C, 31C, 33C, HB-32-26A).

### Task 18: Mechanical Agent Orchestrator

**Owner:** integration-eng
- Create: `src/plugins/sat_maestro/mechanical/agent.py`
- Test: `tests/plugins/sat_maestro/mechanical/test_mechanical_agent.py`

```python
class MechanicalAgent:
    """Orchestrates all mechanical analyses."""
    def __init__(self, bridge: McpBridge, config: SatMaestroConfig):
        self.mass_budget = MassBudgetAnalyzer(bridge, config.mass_margin)
        self.cog = CogCalculator(bridge)
        self.assembly = AssemblyValidator(bridge)
        self.thermal_solver = ThermalNodeModel(bridge)
        self.thermal_checker = ThermalChecker(bridge)
        self.deployment = DeploymentValidator(bridge)
        self.kinematic = KinematicAnalyzer(bridge)
        self.modal = ModalAnalyzer(bridge)
        self.random_vib = RandomVibAnalyzer(bridge)
        self.shock = ShockAnalyzer(bridge)

    async def run_full_analysis(self, ...) -> tuple[list[AnalysisResult], str]:
        """Run all mechanical analyses."""
```

### Task 19: Plugin Tools Registration

**Owner:** integration-eng
- Modify: `src/plugins/sat_maestro/plugin.py`

Add all 15 new `@plugin_tool` methods for mechanical + cross-discipline.

### Task 20: Electrical Agent MCP Migration

**Owner:** integration-eng
- Modify: `src/plugins/sat_maestro/electrical/agent.py`
- Modify: `src/plugins/sat_maestro/electrical/analyzers/*.py`
- Modify: `src/plugins/sat_maestro/electrical/rules/loader.py`
- Modify: `src/plugins/sat_maestro/plugin.py`

Refactor all `GraphOperations` calls to use `McpBridge.neo4j_query()` / `neo4j_write()`.
Remove `neo4j_client.py` and `graph_ops.py` after migration. Update all tests.

### Task 21: Config + Dependencies Update

**Owner:** integration-eng
- Modify: `src/plugins/sat_maestro/config.py`
- Modify: `requirements-sat-maestro.txt`

Add config fields: `mass_margin`, `freecad_mcp_command`, `calculix_path`, `gmsh_mcp_command`.
Add dependencies: `mcp`, `numpy`, `pyNastran`.

### Task 22: Final Integration Test + Commit

**Owner:** Lead
- Run all tests
- Verify 100% of existing tests still pass
- Commit entire mechanical module

```bash
python -m pytest tests/plugins/sat_maestro/ -v --override-ini="addopts="
git add -A
git commit -m "feat(sat-maestro): complete mechanical agent with MCP architecture"
```

---

## Team Assignment Summary

| Task | Owner | Phase | Blocked By |
|------|-------|-------|------------|
| 1: MCP Bridge | integration-eng | 0 | — |
| 2: Graph Models | integration-eng | 0 | — |
| 3: mcp-gmsh | mcp-engineer | 0 | — |
| 4: mcp-calculix | mcp-engineer | 0 | — |
| 5: Mass Budget | structural-eng | 1 | Task 1, 2 |
| 6: CoG Calculator | structural-eng | 1 | Task 1, 2 |
| 7: Assembly Validator | structural-eng | 1 | Task 1, 2 |
| 8: Thermal Solver | thermal-eng | 2 | Task 1, 2 |
| 9: Thermal Checker | thermal-eng | 2 | Task 8 |
| 10: Orbital Cycle | thermal-eng | 2 | Task 8 |
| 11: Deployment | mechanism-eng | 2 | Task 1, 2 |
| 12: Kinematic | mechanism-eng | 2 | Task 11 |
| 13: Modal Analysis | mechanism-eng | 3 | Task 4 |
| 14: Random Vibration | mechanism-eng | 3 | Task 13 |
| 15: Shock Analysis | mechanism-eng | 3 | Task 13 |
| 16: Cross-Discipline | integration-eng | 4 | Task 5-15 |
| 17: ECSS Rules Seed | integration-eng | 4 | Task 2 |
| 18: Mechanical Agent | integration-eng | 4 | Task 5-15 |
| 19: Plugin Tools | integration-eng | 4 | Task 18 |
| 20: Electrical Migration | integration-eng | 4 | Task 1 |
| 21: Config + Deps | integration-eng | 4 | — |
| 22: Final Test | Lead | 5 | All |
