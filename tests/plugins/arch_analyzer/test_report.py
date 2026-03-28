"""Tests for ReportGenerator."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig
from src.plugins.arch_analyzer.report import ReportGenerator


class TestGenerate:
    """Tests for ReportGenerator.generate."""

    def test_cli_format_returns_string(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        result = gen.generate(fmt="cli")
        assert isinstance(result, str)
        assert "Architecture Analysis Report" in result

    def test_markdown_format_has_header(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        result = gen.generate(fmt="markdown")
        assert isinstance(result, str)
        assert "# Architecture Analysis Report" in result

    def test_cli_with_structure_data(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        data = {
            "total_files": 42,
            "total_dirs": 8,
            "technologies": ["Python"],
            "frameworks": ["Flask"],
            "languages": {"Python": 30, "HTML": 12},
        }
        result = gen.generate(structure=data, fmt="cli")
        assert "42" in result
        assert "Python" in result
        assert "Flask" in result

    def test_cli_with_patterns_data(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        data = {
            "architecture_type": "MVC",
            "confidence": 0.9,
            "architecture_scores": {"MVC": 0.9, "Layered": 0.3},
            "design_patterns": ["Singleton", "Factory"],
        }
        result = gen.generate(patterns=data, fmt="cli")
        assert "MVC" in result
        assert "Singleton" in result

    def test_cli_with_metrics_data(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        data = {
            "total_loc": 1500,
            "total_blank_lines": 200,
            "total_comment_lines": 100,
            "total_source_files": 20,
            "total_classes": 5,
            "total_functions": 30,
            "avg_file_size_loc": 75.0,
        }
        result = gen.generate(metrics=data, fmt="cli")
        assert "1,500" in result
        assert "30" in result

    def test_markdown_with_api_data(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        data = {
            "total_count": 3,
            "frameworks": ["Flask"],
            "endpoints": [
                {"method": "GET", "path": "/api/users", "handler": "list_users", "file": "app.py"},
                {"method": "POST", "path": "/api/users", "handler": "create_user", "file": "app.py"},
            ],
        }
        result = gen.generate(api_map=data, fmt="markdown")
        assert "API Endpoints" in result
        assert "GET" in result
        assert "/api/users" in result

    def test_empty_report_no_crash(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        result = gen.generate(fmt="cli")
        assert isinstance(result, str)

    def test_cli_with_dependencies_circular(self) -> None:
        config = ArchAnalyzerConfig()
        gen = ReportGenerator(config)
        data = {
            "files_analyzed": 10,
            "total_internal_edges": 15,
            "total_external_packages": 3,
            "external_deps": ["flask", "sqlalchemy"],
            "circular_deps": [["a", "b", "c", "a"]],
        }
        result = gen.generate(dependencies=data, fmt="cli")
        assert "Circular" in result or "circular" in result
        assert "a" in result
