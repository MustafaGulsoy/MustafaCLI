"""Tests for ProjectStructureAnalyzer."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig
from src.plugins.arch_analyzer.analyzers.structure import (
    ProjectStructureAnalyzer,
    DirectoryNode,
    FileInfo,
    TechStack,
)


class TestBuildTree:
    """Tests for ProjectStructureAnalyzer.build_tree."""

    def test_build_tree_returns_root_node(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        assert isinstance(tree, DirectoryNode)
        assert tree.name == python_flask_project.name

    def test_build_tree_contains_children(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        child_names = {c.name for c in tree.children}
        assert "models" in child_names
        assert "routes" in child_names
        assert "templates" in child_names

    def test_build_tree_contains_files(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        file_names = {Path(f.path).name for f in tree.files}
        assert "app.py" in file_names
        assert "requirements.txt" in file_names

    def test_build_tree_file_info_has_lines(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        app_file = next(f for f in tree.files if f.path.endswith("app.py"))
        assert app_file.lines > 0
        assert app_file.size > 0
        assert app_file.extension == ".py"

    def test_build_tree_raises_for_missing_path(self) -> None:
        analyzer = ProjectStructureAnalyzer()
        with pytest.raises(FileNotFoundError):
            analyzer.build_tree("/nonexistent/path/xyz")

    def test_build_tree_raises_for_file_path(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        with pytest.raises(NotADirectoryError):
            analyzer.build_tree(python_flask_project / "app.py")

    def test_build_tree_respects_max_depth(self, deeply_nested_project: Path) -> None:
        config = ArchAnalyzerConfig(max_depth=3)
        analyzer = ProjectStructureAnalyzer(config)
        tree = analyzer.build_tree(deeply_nested_project)

        # Walk down to verify depth limit
        node = tree
        depth = 0
        while node.children:
            depth += 1
            node = node.children[0]
        assert depth <= 3

    def test_build_tree_ignores_pycache(self, python_flask_project: Path) -> None:
        # Create __pycache__ dir
        pycache = python_flask_project / "__pycache__"
        pycache.mkdir()
        (pycache / "app.cpython-311.pyc").write_bytes(b"\x00" * 50)

        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        child_names = {c.name for c in tree.children}
        assert "__pycache__" not in child_names

    def test_build_tree_empty_project(self, empty_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(empty_project)
        assert tree.children == []
        assert tree.files == []


class TestDetectTechStack:
    """Tests for ProjectStructureAnalyzer.detect_tech_stack."""

    def test_flask_project_detects_python(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(python_flask_project)
        assert "Python" in stack.languages

    def test_flask_project_detects_flask_framework(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(python_flask_project)
        assert "Flask" in stack.frameworks

    def test_flask_project_detects_pip(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(python_flask_project)
        assert "pip" in stack.package_managers

    def test_node_project_detects_javascript(self, node_express_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(node_express_project)
        assert "JavaScript" in stack.languages

    def test_node_project_detects_npm(self, node_express_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(node_express_project)
        assert "npm" in stack.package_managers

    def test_node_project_detects_express(self, node_express_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(node_express_project)
        assert "Express" in stack.frameworks

    def test_fastapi_project_detects_fastapi(self, python_fastapi_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(python_fastapi_project)
        assert "FastAPI" in stack.frameworks

    def test_fastapi_project_detects_pyproject_build(self, python_fastapi_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(python_fastapi_project)
        assert "pyproject" in stack.build_tools

    def test_dotnet_project_detects_csharp(self, dotnet_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(dotnet_project)
        assert "C#" in stack.languages

    def test_dotnet_project_detects_msbuild(self, dotnet_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(dotnet_project)
        assert "msbuild" in stack.build_tools

    def test_empty_project_returns_empty_stack(self, empty_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        stack = analyzer.detect_tech_stack(empty_project)
        assert stack.languages == []
        assert stack.frameworks == []
        assert stack.build_tools == []
        assert stack.package_managers == []


class TestGetFileStats:
    """Tests for ProjectStructureAnalyzer.get_file_stats."""

    def test_stats_count_files(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        stats = analyzer.get_file_stats(tree)
        assert stats["total_files"] > 0

    def test_stats_count_lines(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        stats = analyzer.get_file_stats(tree)
        assert stats["total_lines"] > 0

    def test_stats_has_extensions(self, python_flask_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(python_flask_project)
        stats = analyzer.get_file_stats(tree)
        assert ".py" in stats["extensions"]

    def test_stats_empty_project(self, empty_project: Path) -> None:
        analyzer = ProjectStructureAnalyzer()
        tree = analyzer.build_tree(empty_project)
        stats = analyzer.get_file_stats(tree)
        assert stats["total_files"] == 0
        assert stats["total_lines"] == 0
