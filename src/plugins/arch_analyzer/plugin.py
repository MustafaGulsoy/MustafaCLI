"""Arch-Analyzer Plugin -- Main entry point for MustafaCLI plugin system."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..base import PluginBase, PluginMetadata, plugin_tool
from ...core.tools import ToolResult
from .config import ArchAnalyzerConfig
from .analyzers.structure import ProjectStructureAnalyzer
from .analyzers.dependencies import DependencyAnalyzer
from .analyzers.patterns import PatternDetector
from .analyzers.metrics import CodeMetrics
from .analyzers.api_mapper import ApiMapper
from .report import ReportGenerator

logger = logging.getLogger(__name__)


class ArchAnalyzerPlugin(PluginBase):
    """Arch-Analyzer: Software Architecture Analysis Plugin.

    Scans project directories to detect tech stacks, architectural patterns,
    dependency graphs, code metrics, and API endpoints. No external services
    required -- operates entirely on local filesystem using only stdlib.

    Activate with: mustafacli plugin enable arch-analyzer
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="arch-analyzer",
            version="1.0.0",
            description="Software architecture analysis -- structure, patterns, metrics, APIs",
            author="Kardelen Yazilim",
            requires=[],
            tags=["architecture", "analysis", "metrics", "dependencies", "api"],
            homepage="https://github.com/kardelenyazilim/arch-analyzer",
            license="MIT",
        )

    async def initialize(self) -> None:
        """Initialize configuration and analyzer instances."""
        self.config = ArchAnalyzerConfig.from_env()
        self._structure = ProjectStructureAnalyzer(self.config)
        self._dependencies = DependencyAnalyzer(self.config)
        self._patterns = PatternDetector(self.config)
        self._metrics = CodeMetrics(self.config)
        self._api_mapper = ApiMapper(self.config)
        self._report = ReportGenerator(self.config)
        logger.info("Arch-Analyzer: Initialized (max_depth=%d)", self.config.max_depth)

    # ------------------------------------------------------------------
    # Plugin tools
    # ------------------------------------------------------------------

    @plugin_tool(
        name="arch_analyze_structure",
        description="Scan a project directory to detect tech stack, languages, frameworks, and entry points.",
    )
    def arch_analyze_structure(self, project_dir: str) -> ToolResult:
        """Analyze project structure and tech stack."""
        try:
            result = self._structure.analyze(project_dir)
            return ToolResult(
                success=True,
                output=json.dumps(result, indent=2, ensure_ascii=False),
                metadata=result,
            )
        except Exception as exc:
            logger.error("arch_analyze_structure failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))

    @plugin_tool(
        name="arch_analyze_dependencies",
        description="Build import/dependency graph, detect circular dependencies, and list external packages.",
    )
    def arch_analyze_dependencies(self, project_dir: str) -> ToolResult:
        """Analyze project dependencies and import graph."""
        try:
            result = self._dependencies.analyze(project_dir)
            # Trim internal_deps for output readability
            output = dict(result)
            internal = output.get("internal_deps", {})
            if len(internal) > 50:
                trimmed = dict(list(internal.items())[:50])
                output["internal_deps"] = trimmed
                output["_note"] = f"Showing 50 of {len(internal)} files with internal deps"
            return ToolResult(
                success=True,
                output=json.dumps(output, indent=2, ensure_ascii=False),
                metadata=result,
            )
        except Exception as exc:
            logger.error("arch_analyze_dependencies failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))

    @plugin_tool(
        name="arch_detect_patterns",
        description="Detect architectural patterns (MVC, layered, microservice, etc.) and design patterns.",
    )
    def arch_detect_patterns(self, project_dir: str) -> ToolResult:
        """Detect architectural and design patterns."""
        try:
            result = self._patterns.analyze(project_dir)
            return ToolResult(
                success=True,
                output=json.dumps(result, indent=2, ensure_ascii=False),
                metadata=result,
            )
        except Exception as exc:
            logger.error("arch_detect_patterns failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))

    @plugin_tool(
        name="arch_code_metrics",
        description="Calculate code metrics: LOC, file counts, classes, functions, complexity estimates.",
    )
    def arch_code_metrics(self, project_dir: str) -> ToolResult:
        """Calculate code metrics for the project."""
        try:
            result = self._metrics.analyze(project_dir)
            return ToolResult(
                success=True,
                output=json.dumps(result, indent=2, ensure_ascii=False),
                metadata=result,
            )
        except Exception as exc:
            logger.error("arch_code_metrics failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))

    @plugin_tool(
        name="arch_map_apis",
        description="Detect REST API endpoints across frameworks (FastAPI, Flask, Express, ASP.NET, Django, Spring).",
    )
    def arch_map_apis(self, project_dir: str) -> ToolResult:
        """Map API endpoints in the project."""
        try:
            result = self._api_mapper.analyze(project_dir)
            return ToolResult(
                success=True,
                output=json.dumps(result, indent=2, ensure_ascii=False),
                metadata=result,
            )
        except Exception as exc:
            logger.error("arch_map_apis failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))

    @plugin_tool(
        name="arch_full_report",
        description="Run all architecture analyzers and produce a comprehensive report. "
                    "Set format to 'markdown' for MD output or 'cli' (default) for plain text.",
    )
    def arch_full_report(self, project_dir: str, format: str = "cli") -> ToolResult:
        """Run all analyzers and generate a full architecture report."""
        try:
            structure = self._structure.analyze(project_dir)
            dependencies = self._dependencies.analyze(project_dir)
            patterns = self._patterns.analyze(project_dir)
            metrics = self._metrics.analyze(project_dir)
            api_map = self._api_mapper.analyze(project_dir)

            report = self._report.generate(
                structure=structure,
                dependencies=dependencies,
                patterns=patterns,
                metrics=metrics,
                api_map=api_map,
                fmt=format,
            )

            return ToolResult(
                success=True,
                output=report,
                metadata={
                    "structure": structure,
                    "dependencies": {
                        k: v for k, v in dependencies.items()
                        if k != "internal_deps"
                    },
                    "patterns": patterns,
                    "metrics": {
                        k: v for k, v in metrics.items()
                        if k != "largest_files"
                    },
                    "api_map": api_map,
                },
            )
        except Exception as exc:
            logger.error("arch_full_report failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))
