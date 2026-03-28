"""Tests for CodeMetrics."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig
from src.plugins.arch_analyzer.analyzers.metrics import (
    CodeMetrics,
    FileMetrics,
    ProjectMetrics,
)


class TestAnalyzeFile:
    """Tests for CodeMetrics.analyze_file."""

    def test_counts_lines(self, python_flask_project: Path) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_file(python_flask_project / "app.py")
        assert result.lines_total > 0
        assert result.lines_code > 0

    def test_counts_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "blank.py"
        f.write_text("x = 1\n\n\ny = 2\n")
        metrics = CodeMetrics()
        result = metrics.analyze_file(f)
        assert result.lines_blank == 2
        assert result.lines_code == 2

    def test_counts_comment_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "comments.py"
        f.write_text("# This is a comment\nx = 1\n# Another comment\n")
        metrics = CodeMetrics()
        result = metrics.analyze_file(f)
        assert result.lines_comment == 2
        assert result.lines_code == 1

    def test_detects_functions(self, tmp_path: Path) -> None:
        f = tmp_path / "funcs.py"
        f.write_text(textwrap.dedent("""\
            def foo():
                pass

            def bar():
                pass

            async def baz():
                pass
        """))
        metrics = CodeMetrics()
        result = metrics.analyze_file(f)
        assert result.functions == 3

    def test_detects_classes(self, tmp_path: Path) -> None:
        f = tmp_path / "classes.py"
        f.write_text(textwrap.dedent("""\
            class Foo:
                pass

            class Bar:
                def method(self):
                    pass
        """))
        metrics = CodeMetrics()
        result = metrics.analyze_file(f)
        assert result.classes == 2
        assert result.functions == 1  # the method

    def test_nonexistent_file(self) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_file("/nonexistent/file.py")
        assert result.lines_total == 0
        assert result.lines_code == 0

    def test_complexity_for_branching_code(self, tmp_path: Path) -> None:
        f = tmp_path / "branchy.py"
        f.write_text(textwrap.dedent("""\
            def complex_func(x, y):
                if x > 0:
                    if y > 0:
                        return x + y
                    else:
                        return x
                elif x == 0:
                    for i in range(y):
                        if i % 2 == 0:
                            print(i)
                else:
                    try:
                        return x / y
                    except ZeroDivisionError:
                        return 0
        """))
        metrics = CodeMetrics()
        result = metrics.analyze_file(f)
        assert result.complexity >= 5  # multiple branches


class TestAnalyzeProject:
    """Tests for CodeMetrics.analyze_project."""

    def test_project_aggregates(self, python_flask_project: Path) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_project(python_flask_project)
        assert result.total_files > 0
        assert result.total_lines > 0
        assert result.total_code_lines > 0

    def test_language_breakdown(self, python_flask_project: Path) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_project(python_flask_project)
        assert ".py" in result.language_breakdown
        assert result.language_breakdown[".py"] > 0

    def test_empty_project(self, empty_project: Path) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_project(empty_project)
        assert result.total_files == 0
        assert result.total_lines == 0

    def test_files_list_populated(self, python_flask_project: Path) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_project(python_flask_project)
        assert len(result.files) == result.total_files

    def test_mixed_language_project(self, node_express_project: Path) -> None:
        metrics = CodeMetrics()
        result = metrics.analyze_project(node_express_project)
        assert ".js" in result.language_breakdown or ".json" in result.language_breakdown
