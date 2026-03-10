# SAT-MAESTRO Plugin Design Spec

> Satellite Multidisciplinary Engineering & System Trust Officer — MustafaCLI Plugin

## Overview

SAT-MAESTRO is an optional plugin for MustafaCLI that provides satellite engineering analysis capabilities. It extends the existing plugin system (`PluginBase`) without modifying the core. Users activate it via `mustafacli plugin enable sat-maestro`.

**MVP Scope:** Electrical Agent + Neo4j knowledge graph. Mechanical and ECSS Compliance agents will be added in future phases.

## Architecture: Micro-Plugin Family

Single plugin package with modular internals:

- `sat-maestro-core` — Neo4j client, graph models, graph operations, report generator
- `sat-maestro-electrical` — ElectricalAgent with parsers, analyzers, rule engine

Future modules: `sat-maestro-mechanical`, `sat-maestro-ecss`

Entry point: `SatMaestroPlugin(PluginBase)` — single registration with MustafaCLI plugin registry.

## Module Structure

```
src/plugins/sat_maestro/
├── __init__.py              # SatMaestroPlugin (PluginBase subclass)
├── config.py                # SatMaestroConfig dataclass
│
├── core/
│   ├── __init__.py
│   ├── neo4j_client.py      # Async Neo4j connection management
│   ├── graph_models.py      # Component, Pin, Net, Connector, EcssRule dataclasses
│   ├── graph_ops.py         # GraphOperations CRUD class
│   └── report.py            # ReportGenerator: CLI/JSON/HTML/Neo4j
│
├── electrical/
│   ├── __init__.py
│   ├── agent.py             # ElectricalAgent orchestrator
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── kicad.py         # KiCad .kicad_sch / .kicad_pcb parser
│   │   ├── gerber.py        # Gerber RS-274X parser (pygerber)
│   │   └── pdf_vision.py    # PDF schematic → LLM vision analysis
│   ├── analyzers/
│   │   ├── __init__.py
│   │   ├── pin_to_pin.py    # Pin-to-pin continuity verification
│   │   ├── power_budget.py  # Power budget analysis
│   │   └── connector.py     # Connector derating & matching
│   └── rules/
│       ├── __init__.py
│       └── loader.py        # Load ECSS rules from Neo4j
│
├── db/
│   ├── __init__.py
│   └── seed_rules.py        # Seed default ECSS rules into Neo4j
│
└── templates/
    └── report.html           # Jinja2 HTML report template

tests/plugins/sat_maestro/
├── conftest.py
├── test_plugin.py
├── core/
│   ├── test_neo4j_client.py
│   ├── test_graph_ops.py
│   └── test_report.py
└── electrical/
    ├── test_agent.py
    ├── test_kicad_parser.py
    ├── test_gerber_parser.py
    ├── test_pin_to_pin.py
    └── test_power_budget.py
```

## Neo4j Graph Model

### Nodes

| Label | Properties |
|-------|-----------|
| `Component` | id, name, type (IC/CONNECTOR/PASSIVE/MODULE), subsystem, properties |
| `Pin` | id, name, direction (INPUT/OUTPUT/BIDIRECTIONAL/POWER), voltage, current_max |
| `Net` | id, name, type (power/signal/ground) |
| `Connector` | id, name, pin_count, series |
| `EcssRule` | id, standard, clause, severity, category, check_expression, message_template |
| `AnalysisRun` | id, timestamp, source_file, status |
| `Violation` | rule_id, severity, message, component_path |

### Relationships

| Relationship | From → To |
|-------------|-----------|
| `HAS_PIN` | Component/Connector → Pin |
| `CONNECTED_TO` | Pin → Pin (with net_name, trace_width) |
| `CARRIES` | Net → Pin |
| `MATES_WITH` | Connector → Connector |
| `APPLIES_TO` | EcssRule → Component/Connector/Net (with condition) |
| `FOUND` | AnalysisRun → Violation |
| `ANALYZED` | AnalysisRun → Component |

## Plugin Entry Point & Lifecycle

```python
class SatMaestroPlugin(PluginBase):
    metadata = PluginMetadata(
        name="sat-maestro",
        version="0.1.0",
        description="Satellite Engineering Analysis - Electrical Agent",
        author="Kardelen Yazilim",
        dependencies=["neo4j", "pygerber", "sexpdata", "jinja2"],
    )

    async def initialize(self):
        self.config = SatMaestroConfig.from_env()
        self.neo4j = Neo4jClient(self.config)
        await self.neo4j.connect()
        await seed_default_rules(self.neo4j)
        self.electrical = ElectricalAgent(self.neo4j, self.config)

    async def shutdown(self):
        await self.neo4j.close()
```

## Plugin Tools

| Tool | Description |
|------|------------|
| `sat_import_kicad` | Parse KiCad project and load into Neo4j graph |
| `sat_import_gerber` | Parse Gerber files and load into Neo4j graph |
| `sat_analyze_pdf` | Analyze PDF schematic via LLM vision |
| `sat_verify_pins` | Run pin-to-pin continuity verification |
| `sat_power_budget` | Run power budget analysis |
| `sat_check_connectors` | Run connector derating & matching check |
| `sat_check_compliance` | Run all ECSS rules |
| `sat_report` | Generate report (CLI/JSON/HTML/Neo4j) |
| `sat_graph_query` | Execute custom Cypher query |
| `sat_seed_rules` | Load custom ECSS rules |

## Configuration

```python
@dataclass
class SatMaestroConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "satmaestro"
    report_output_dir: str = "./sat-reports"
    default_report_format: str = "cli"
    llm_vision_enabled: bool = True
    derating_factor: float = 0.75
```

## Electrical Agent Internals

### Parsers

- **KiCadParser**: Reads `.kicad_sch`/`.kicad_pcb` via `sexpdata`, extracts Components, Pins, Nets
- **GerberParser**: Reads RS-274X via `pygerber`, extracts Pads, Traces, Layers
- **PdfVisionParser**: Converts PDF pages to images, sends to LLM vision, parses structured JSON response with confidence scoring

### Analyzers

- **PinToPinAnalyzer**: Traces paths in Neo4j graph, detects OPEN (missing) and SHORT (unexpected) connections
- **PowerBudgetAnalyzer**: Builds power tree from graph, calculates current sums per node, checks derating limits and margins
- **ConnectorAnalyzer**: Validates MATES_WITH pairs (pin count, voltage/current compatibility, series matching, ECSS derating)

### Common Output

```python
@dataclass
class AnalysisResult:
    analyzer: str
    status: AnalysisStatus  # PASS, WARN, FAIL
    timestamp: datetime
    violations: list[Violation]
    summary: dict[str, Any]
    metadata: dict[str, Any]
```

## Report System

4 output formats:

1. **CLI** — Rich tables with colored pass/warn/fail indicators
2. **JSON** — Structured report for CI/CD integration (includes exit_code)
3. **HTML** — Jinja2 template with summary dashboard, violation table, inline SVG power tree
4. **Neo4j** — Stores AnalysisRun + Violations in graph, returns Neo4j Browser URL

## ECSS Rule Engine

Rules stored as `EcssRule` nodes in Neo4j with `APPLIES_TO` relationships.

- Safe expression evaluator (AST-based, no eval/exec)
- Only allows: comparison, arithmetic, attribute access
- MVP seeds ~15-20 rules from ECSS-E-ST-20C (connector derating, wire derating, power margins, grounding, EMC basics)
- Users can add custom rules via `sat_seed_rules` tool

## Infrastructure

**Docker Compose override** (`deployment/docker-compose.sat-maestro.yml`):
- Neo4j 5.x container
- Ports: 7687 (Bolt), 7474 (Browser)
- Volume: neo4j-data

**Dependencies** (`requirements-sat-maestro.txt`):
- neo4j[async]
- pygerber
- sexpdata
- jinja2
- rich (already in project)

## User Experience

```bash
# Enable plugin
mustafacli plugin enable sat-maestro

# Start Neo4j
docker compose -f deployment/docker-compose.sat-maestro.yml up -d

# Import and analyze
mustafacli> /sat_import_kicad ./power-board.kicad_sch
mustafacli> /sat_verify_pins --subsystem EPS
mustafacli> /sat_check_compliance --format html --output ./reports/
```

## Future Phases

- **Phase 2**: Mechanical Agent (static/dynamic loads, thermal margins, STEP/IGES parsing)
- **Phase 3**: ECSS Compliance Agent (full standards coverage, cross-discipline checks)
- **Phase 4**: Cross-discipline analysis (power budget vs software modes, thermal-electrical coupling)
