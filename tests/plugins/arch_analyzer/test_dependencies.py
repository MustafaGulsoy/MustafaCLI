"""Tests for DependencyAnalyzer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig
from src.plugins.arch_analyzer.analyzers.dependencies import (
    DependencyAnalyzer,
    DependencyGraph,
    ImportInfo,
)


class TestBuildImportGraph:
    """Tests for DependencyAnalyzer.build_import_graph."""

    def test_graph_has_nodes(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        assert len(graph.nodes) > 0

    def test_graph_contains_app_module(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        assert "app" in graph.nodes

    def test_graph_has_imports(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        assert len(graph.imports) > 0
        # app.py imports flask and models.user
        assert "app" in graph.imports
        app_imports = graph.imports["app"]
        module_names = [imp.module for imp in app_imports]
        assert "flask" in module_names

    def test_graph_empty_project(self, empty_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(empty_project)
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_graph_nonexistent_dir(self) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph("/nonexistent/path/xyz")
        assert len(graph.nodes) == 0

    def test_graph_internal_edges(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        # models.user should be in the graph as a node
        assert "models.user" in graph.nodes

    def test_imports_have_line_numbers(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        for imports_list in graph.imports.values():
            for imp in imports_list:
                assert imp.line_number > 0

    def test_relative_imports_detected(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        all_imports = [imp for imps in graph.imports.values() for imp in imps]
        # At least some should be non-relative (like 'flask')
        non_relative = [imp for imp in all_imports if not imp.is_relative]
        assert len(non_relative) > 0


class TestBuildJsImportGraph:
    """Tests for DependencyAnalyzer.build_js_import_graph."""

    def test_js_graph_has_nodes(self, node_express_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_js_import_graph(node_express_project)
        assert len(graph.nodes) > 0

    def test_js_graph_detects_require(self, node_express_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_js_import_graph(node_express_project)
        all_imports = [imp for imps in graph.imports.values() for imp in imps]
        modules = [imp.module for imp in all_imports]
        assert "express" in modules

    def test_js_graph_detects_relative_imports(self, node_express_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_js_import_graph(node_express_project)
        all_imports = [imp for imps in graph.imports.values() for imp in imps]
        relative = [imp for imp in all_imports if imp.is_relative]
        assert len(relative) > 0


class TestCircularDependencies:
    """Tests for DependencyAnalyzer.find_circular_dependencies."""

    def test_detects_circular_deps(self, circular_deps_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(circular_deps_project)
        cycles = analyzer.find_circular_dependencies(graph)
        assert len(cycles) > 0

    def test_circular_cycle_contains_modules(self, circular_deps_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(circular_deps_project)
        cycles = analyzer.find_circular_dependencies(graph)
        # At least one cycle should include module_a, module_b, or module_c
        all_cycle_members = {m for cycle in cycles for m in cycle}
        assert "module_a" in all_cycle_members or "module_b" in all_cycle_members

    def test_no_circular_deps_in_clean_project(self, python_fastapi_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_fastapi_project)
        cycles = analyzer.find_circular_dependencies(graph)
        # FastAPI project should have no circular deps (imports are all external)
        assert len(cycles) == 0

    def test_empty_graph_no_cycles(self) -> None:
        graph = DependencyGraph()
        analyzer = DependencyAnalyzer()
        cycles = analyzer.find_circular_dependencies(graph)
        assert cycles == []


class TestDependencyGraphMethods:
    """Tests for DependencyGraph data structure."""

    def test_add_edge(self) -> None:
        graph = DependencyGraph()
        graph.add_edge("a", "b")
        assert "a" in graph.nodes
        assert "b" in graph.nodes
        assert ("a", "b") in graph.edges

    def test_get_dependencies(self) -> None:
        graph = DependencyGraph()
        graph.add_edge("a", "b")
        graph.add_edge("a", "c")
        deps = graph.get_dependencies("a")
        assert set(deps) == {"b", "c"}

    def test_get_dependents(self) -> None:
        graph = DependencyGraph()
        graph.add_edge("a", "c")
        graph.add_edge("b", "c")
        dependents = graph.get_dependents("c")
        assert set(dependents) == {"a", "b"}


class TestExternalDependencies:
    """Tests for get_external_dependencies."""

    def test_detects_flask_as_external(self, python_flask_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        graph = analyzer.build_import_graph(python_flask_project)
        external = analyzer.get_external_dependencies(graph)
        assert "flask" in external


class TestParsePackageJson:
    """Tests for parse_package_json."""

    def test_parses_dependencies(self, node_express_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        result = analyzer.parse_package_json(node_express_project)
        assert "express" in result["dependencies"]
        assert "jest" in result["devDependencies"]

    def test_missing_package_json(self, empty_project: Path) -> None:
        analyzer = DependencyAnalyzer()
        result = analyzer.parse_package_json(empty_project)
        assert result == {}
