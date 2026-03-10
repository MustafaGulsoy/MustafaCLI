# SAT-MAESTRO Mechanical Agent Design Spec

> Satellite Mechanical Engineering — Structural, Thermal, Mechanism, Vibration + Cross-Discipline Analysis

## Overview

SAT-MAESTRO Mechanical Agent extends the existing SAT-MAESTRO plugin with full mechanical engineering analysis capabilities. Unlike the electrical agent which uses direct Neo4j client calls, the mechanical agent follows an **MCP-first architecture** — all external tools (Neo4j, FreeCAD, CalculiX, Gmsh) are accessed via MCP servers. The existing electrical agent will also be migrated to MCP as part of this work.

**Scope:** Structural + Thermal + Mechanism + Vibration + Cross-Discipline analysis.

**Architecture:** Orchestrator pattern — SAT-MAESTRO coordinates MCP servers, does not implement solvers.

**Key Decision:** Simple calculations (mass budget, CoG, lumped-parameter thermal) run locally. Complex analysis (FEM, multi-body dynamics) delegates to external tools via MCP.

## MCP Server Landscape

### External (existing, integrate):

| MCP Server | Source | Purpose |
|------------|--------|---------|
| `neo4j/mcp` | [neo4j/mcp](https://github.com/neo4j/mcp) | Official Neo4j MCP — replaces custom neo4j_client.py |
| `freecad-mcp` | [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) / [contextform/freecad-mcp](https://github.com/contextform/freecad-mcp) | CAD import, mass/CoG/volume, STEP/IGES |

### Internal (we build):

| MCP Server | Purpose |
|------------|---------|
| `mcp-calculix` | CalculiX FEM solver wrapper (static, modal, thermal, buckling) |
| `mcp-gmsh` | Gmsh mesh generator (STEP→mesh, refinement, format conversion) |

### Future (Tier 2/3):

| MCP Server | Purpose |
|------------|---------|
| `mcp-mbdyn` | Multi-body dynamics (mechanism simulation) |
| `mcp-paraview` | FEM result visualization |
| `mcp-openmdao` | Multidisciplinary optimization |
| `mcp-openradioss` | Crash/impact analysis |
| `mcp-elmer` | Multi-physics (electromagnetic + thermal) |

## Neo4j Graph Model — Mechanical Nodes

### New Node Types

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `Structure` | Structural element (panel, bracket, beam) | id, name, material, mass, volume, cog_x/y/z |
| `Assembly` | Assembly group (subsystem level) | id, name, total_mass, cog_x/y/z, level |
| `ThermalNode` | Thermal node (lumped parameter) | id, name, temperature, capacity, power_dissipation |
| `ThermalConductance` | Thermal link between nodes | id, type (conduction/radiation/convection), value |
| `Mechanism` | Deployment mechanism | id, name, type (hinge/latch/motor), state, dof |
| `Joint` | Mechanism joint | id, type (revolute/prismatic/fixed), min_angle, max_angle, torque |
| `FemModel` | FEM analysis model | id, name, solver, node_count, element_count, solution_type |
| `FemResult` | FEM result set | id, type (modal/static/thermal), max_stress, max_displacement, safety_factor |
| `Material` | Material definition | id, name, density, youngs_modulus, poisson, thermal_conductivity, cte, yield_strength |
| `LoadCase` | Load case | id, name, type (quasi-static/random-vib/shock/thermal-cycle), magnitude |

### New Relationships

```cypher
(Assembly)-[:CONTAINS]->(Structure)
(Assembly)-[:CONTAINS]->(Assembly)
(Structure)-[:MADE_OF]->(Material)
(Structure)-[:HAS_THERMAL_NODE]->(ThermalNode)
(ThermalNode)-[:CONDUCTS_TO {value, type}]->(ThermalNode)
(Assembly)-[:HAS_MECHANISM]->(Mechanism)
(Mechanism)-[:HAS_JOINT]->(Joint)
(Joint)-[:CONNECTS]->(Structure, Structure)
(FemModel)-[:MODELS]->(Assembly)
(FemModel)-[:HAS_RESULT]->(FemResult)
(FemModel)-[:USES_LOAD]->(LoadCase)
```

### Cross-Discipline Relationships (electrical ↔ mechanical)

```cypher
(Structure)-[:MOUNTS]->(Component)
(ThermalNode)-[:DISSIPATES_FROM]->(Component)
(Connector)-[:ATTACHED_TO]->(Structure)
(Net)-[:ROUTED_THROUGH]->(Assembly)
```

## Module Structure

```
src/plugins/sat_maestro/
├── core/
│   ├── graph_models.py            # EXTEND: add mechanical dataclasses
│   ├── mcp_bridge.py              # NEW: central MCP server call layer
│   ├── report.py                  # EXTEND: mechanical report sections
│   ├── neo4j_client.py            # REMOVE (replaced by neo4j/mcp)
│   └── graph_ops.py               # REMOVE (replaced by neo4j/mcp via mcp_bridge)
│
├── electrical/                    # EXISTING (refactor: migrate to MCP bridge)
│
├── mechanical/
│   ├── __init__.py
│   ├── agent.py                   # MechanicalAgent orchestrator
│   ├── structural/
│   │   ├── mass_budget.py         # Mass budget analysis
│   │   ├── cog_calculator.py      # Center of gravity calculation
│   │   └── assembly_validator.py  # Assembly validation
│   ├── thermal/
│   │   ├── node_model.py          # Simple lumped-parameter solver
│   │   ├── thermal_checker.py     # Temperature limit validation
│   │   └── orbital_cycle.py       # Orbital thermal cycle analysis
│   ├── mechanism/
│   │   ├── deployment.py          # Deployment sequence/angle validation
│   │   └── kinematic.py           # Kinematic + kinetic analysis
│   ├── vibration/
│   │   ├── modal.py               # Modal analysis result evaluation
│   │   ├── random_vib.py          # Random vibration analysis
│   │   └── shock.py               # Shock analysis
│   └── rules/
│       └── ecss_mechanical.py     # ECSS-E-ST-32/33/31 mechanical rules
│
├── cross_discipline/
│   ├── __init__.py
│   ├── agent.py                   # CrossDisciplineAgent
│   ├── mass_thermal.py            # Mass ↔ thermal correlation
│   ├── electrical_thermal.py      # Electrical ↔ thermal (power dissipation)
│   ├── harness_routing.py         # Cable routing validation
│   └── mounting_check.py          # Mounting compatibility check
│
└── mcp_servers/
    ├── calculix/
    │   ├── server.py              # MCP server main
    │   ├── solver.py              # CalculiX CLI wrapper
    │   └── result_parser.py       # .frd/.dat result reader
    └── gmsh/
        ├── server.py              # MCP server main
        └── mesher.py              # Gmsh Python API wrapper
```

## MCP Server Tool Definitions

### mcp-calculix

| Tool | Description | Parameters |
|------|-------------|------------|
| `ccx_solve_static` | Static structural analysis | input_file, num_cpus |
| `ccx_solve_modal` | Modal (frequency) analysis | input_file, num_modes, frequency_range |
| `ccx_solve_thermal` | Thermal analysis (steady/transient) | input_file, time_steps |
| `ccx_solve_buckling` | Buckling analysis | input_file, num_modes |
| `ccx_read_results` | Read .frd result file | result_file, field (stress/displacement/temperature) |
| `ccx_read_dat` | Read .dat numeric output | dat_file, dataset |
| `ccx_check_input` | Input file syntax check | input_file |
| `ccx_get_version` | CalculiX version info | — |

### mcp-gmsh

| Tool | Description | Parameters |
|------|-------------|------------|
| `gmsh_mesh_from_step` | Generate mesh from STEP | step_file, element_size, element_type, order |
| `gmsh_mesh_from_geo` | Generate mesh from .geo | geo_file, element_size |
| `gmsh_refine_region` | Regional mesh refinement | mesh_file, region_box, target_size |
| `gmsh_convert` | Format conversion | input_file, output_format (inp/bdf/vtk) |
| `gmsh_quality_check` | Mesh quality report | mesh_file, metric |
| `gmsh_info` | Mesh statistics | mesh_file |

## MCP Bridge

Central layer for all MCP server communication:

```python
class McpBridge:
    async def neo4j_query(self, cypher: str, params: dict) -> list[dict]
    async def neo4j_schema(self) -> dict

    async def freecad_import(self, file_path: str) -> dict
    async def freecad_mass_props(self, body_name: str) -> dict
    async def freecad_export(self, format: str) -> str

    async def gmsh_generate(self, geometry: str, element_size: float) -> str
    async def gmsh_refine(self, mesh_path: str, regions: list) -> str

    async def calculix_solve(self, input_file: str, solver_type: str) -> dict
    async def calculix_modal(self, input_file: str, num_modes: int) -> list[dict]
    async def calculix_results(self, result_file: str) -> dict
```

## Plugin Tools

### Structural
- `sat_import_step` — STEP/IGES import via FreeCAD MCP, write structure tree to Neo4j
- `sat_mass_budget` — Mass budget analysis with margins and subsystem breakdown
- `sat_cog_analysis` — Center of gravity + inertia tensor calculation
- `sat_structural_analyze` — Full structural analysis (mesh → FEM → results → ECSS check)

### Thermal
- `sat_thermal_import` — Thermal model import (ESATAN/CSV node-conductance)
- `sat_thermal_solve` — Simple lumped-parameter thermal solution (local)
- `sat_thermal_check` — Temperature limit validation (operational/non-operational)
- `sat_thermal_orbital` — Orbital thermal cycle analysis (hot/cold case)

### Mechanism
- `sat_mechanism_define` — Define mechanism (joints, limits, sequence)
- `sat_deployment_verify` — Deployment sequence and angle validation
- `sat_kinematic_check` — Kinematic + kinetic analysis (torque margin, friction)

### Vibration
- `sat_modal_analyze` — Modal analysis via CalculiX MCP
- `sat_random_vib` — Random vibration analysis (PSD input, RMS output)
- `sat_shock_analyze` — Shock analysis (SRS comparison)

### Cross-Discipline
- `sat_cross_check` — Full cross-discipline check (electrical ↔ mechanical ↔ thermal)
- `sat_power_thermal_map` — Power dissipation → thermal node mapping
- `sat_harness_route` — Cable routing validation (mass, length, mounting points)

## ECSS Mechanical Rules (40+ rules)

### ECSS-E-ST-32C (Structural)
- Yield safety factor ≥ 1.5
- Ultimate safety factor ≥ 2.0
- Buckling safety factor ≥ 2.5
- Mass margin ≥ 10%
- CoG offset within limits
- First lateral frequency ≥ 15 Hz (launcher-dependent)
- First axial frequency ≥ 35 Hz

### ECSS-E-ST-31C (Thermal)
- Operational temperature limits
- Thermal gradient limits
- Heater power margin ≥ 25%
- Radiator area margin ≥ 20%
- Thermal cycle life qualification

### ECSS-E-ST-33C (Mechanism)
- Deployment torque margin ≥ 200%
- Latch force margin ≥ 150%
- Mechanism life factor ≥ 4x
- Backlash limits
- Lubrication temperature limits

### ECSS-E-HB-32-26A (Vibration)
- Random vibration gRMS limits
- Shock SRS margin ≥ 1.5x
- Fatigue life factor ≥ 4x
- Coupled load margin (MoS ≥ 0)

## Full Analysis Flow Example

```
User: "sat_structural_analyze satellite.step"

1. freecad-mcp → STEP import → mass/CoG/inertia
2. neo4j/mcp   → Create Structure + Assembly + Material nodes
3. mcp-gmsh    → Generate FEM mesh (2nd order tet)
4. mcp-gmsh    → Mesh quality check
5. mcp-calculix → Modal analysis (first 20 modes)
6. mcp-calculix → Quasi-static analysis (launch loads)
7. neo4j/mcp   → Create FemModel + FemResult nodes
8. ECSS check  → Frequency > 35Hz? Safety factor > 1.5?
9. neo4j/mcp   → Create Violation nodes (if any)
10. Report     → CLI/JSON/HTML report
```

## Implementation Strategy — Claude Teams

### Team Members

| Member | Role | Responsibility |
|--------|------|----------------|
| Lead | Orchestrator | Task management, review, integration |
| mcp-engineer | MCP Server Dev | mcp-calculix + mcp-gmsh servers |
| structural-eng | Structural Engineer | structural/ module + mass/CoG + FEM integration |
| thermal-eng | Thermal Engineer | thermal/ module + simple solver + orbital cycle |
| mechanism-eng | Mechanism Engineer | mechanism/ + vibration/ modules |
| integration-eng | Integration Engineer | MCP bridge + Neo4j migration + cross_discipline/ + plugin tools |

### Phase Plan

```
Phase 0: [mcp-engineer] Write MCP servers (calculix + gmsh)
         [integration-eng] MCP bridge + Neo4j official MCP migration
              ↓
Phase 1: [structural-eng] Structural module (mass_budget, cog, assembly)
              ↓
Phase 2: [thermal-eng] Thermal module (node_model, checker, orbital)
         [mechanism-eng] Mechanism module (deployment, kinematic)  ← parallel
              ↓
Phase 3: [mechanism-eng] Vibration module (modal, random_vib, shock)
              ↓
Phase 4: [integration-eng] Cross-discipline + plugin tools + ECSS seed
              ↓
Phase 5: [Lead] Final review + test + commit
```

## Migration: Electrical Agent → MCP

The existing electrical agent uses custom `neo4j_client.py` and `graph_ops.py`. As part of this work:

1. Create `mcp_bridge.py` as the central MCP communication layer
2. Refactor electrical agent to use `mcp_bridge.neo4j_query()` instead of direct driver calls
3. Remove `neo4j_client.py` and `graph_ops.py` after migration
4. Update all tests to mock MCP bridge instead of Neo4j driver
