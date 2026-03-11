"""SAT-MAESTRO configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SatMaestroConfig:
    """Configuration for SAT-MAESTRO plugin."""

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "satmaestro"
    neo4j_database: str = "neo4j"
    report_output_dir: str = "./sat-reports"
    default_report_format: str = "cli"  # cli, json, html, all
    llm_vision_enabled: bool = True
    derating_factor: float = 0.75  # ECSS default connector derating
    ollama_url: str = "http://localhost:11434"
    vision_model: str = "llava:13b"  # Ollama vision model
    # Mechanical analysis config
    mass_margin: float = 0.20  # 20% system-level mass margin
    freecad_mcp_command: str = "python -m freecad_mcp"
    calculix_path: str = "ccx"  # CalculiX executable path
    gmsh_mcp_command: str = "python -m sat_maestro_gmsh_mcp"

    @classmethod
    def from_env(cls) -> SatMaestroConfig:
        """Load configuration from environment variables."""
        return cls(
            neo4j_uri=os.getenv("SAT_MAESTRO_NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("SAT_MAESTRO_NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("SAT_MAESTRO_NEO4J_PASSWORD", "satmaestro"),
            neo4j_database=os.getenv("SAT_MAESTRO_NEO4J_DATABASE", "neo4j"),
            report_output_dir=os.getenv("SAT_MAESTRO_REPORT_DIR", "./sat-reports"),
            default_report_format=os.getenv("SAT_MAESTRO_REPORT_FORMAT", "cli"),
            llm_vision_enabled=os.getenv("SAT_MAESTRO_LLM_VISION", "true").lower() == "true",
            derating_factor=float(os.getenv("SAT_MAESTRO_DERATING_FACTOR", "0.75")),
            ollama_url=os.getenv("SAT_MAESTRO_OLLAMA_URL", "http://localhost:11434"),
            vision_model=os.getenv("SAT_MAESTRO_VISION_MODEL", "llava:13b"),
            mass_margin=float(os.getenv("SAT_MAESTRO_MASS_MARGIN", "0.20")),
            freecad_mcp_command=os.getenv("SAT_MAESTRO_FREECAD_MCP_CMD", "python -m freecad_mcp"),
            calculix_path=os.getenv("SAT_MAESTRO_CALCULIX_PATH", "ccx"),
            gmsh_mcp_command=os.getenv("SAT_MAESTRO_GMSH_MCP_CMD", "python -m sat_maestro_gmsh_mcp"),
        )
