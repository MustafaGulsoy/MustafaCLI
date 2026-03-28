"""Plugin catalog — defines available plugins and their install requirements."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PluginInfo:
    """Metadata for an installable plugin."""
    name: str
    description: str
    requirements_file: str  # relative to project root
    docker_compose: str = ""  # optional docker-compose file
    env_vars: dict[str, str] = field(default_factory=dict)  # default env values
    post_install_notes: list[str] = field(default_factory=list)


# All known plugins
PLUGIN_CATALOG: dict[str, PluginInfo] = {
    "sat-maestro": PluginInfo(
        name="sat-maestro",
        description="Satellite Engineering Analysis — Electrical & Mechanical Agents with ECSS rules",
        requirements_file="requirements-sat-maestro.txt",
        docker_compose="deployment/docker-compose.sat-maestro.yml",
        env_vars={
            "SAT_MAESTRO_NEO4J_URI": "bolt://localhost:7687",
            "SAT_MAESTRO_NEO4J_USER": "neo4j",
            "SAT_MAESTRO_NEO4J_PASSWORD": "satmaestro",
        },
        post_install_notes=[
            "Neo4j gerekli: docker compose -f deployment/docker-compose.sat-maestro.yml up -d",
            "Neo4j Browser: http://localhost:7474 (neo4j / satmaestro)",
            "MCP durumu: mustafa --mcp-status",
        ],
    ),
    "arch-analyzer": PluginInfo(
        name="arch-analyzer",
        description="Software Architecture Analyzer — tech stack, dependencies, patterns, metrics, API mapping",
        requirements_file="",  # no extra deps, stdlib only
        post_install_notes=[
            "Hazir! Herhangi bir dizinde: mustafa arch_full_report",
            "Ek bagimlilk gerektirmez — sadece Python stdlib kullanir",
        ],
    ),
}
