"""Code metrics - LOC, complexity, file statistics."""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ArchAnalyzerConfig


@dataclass
class FileMetrics:
    """Metrics for a single file."""

    path: str
    lines_total: int = 0
    lines_code: int = 0
    lines_comment: int = 0
    lines_blank: int = 0
    functions: int = 0
    classes: int = 0
    complexity: int = 0


@dataclass
class ProjectMetrics:
    """Aggregate metrics for the whole project."""

    total_files: int = 0
    total_lines: int = 0
    total_code_lines: int = 0
    total_comment_lines: int = 0
    total_blank_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0
    average_complexity: float = 0.0
    files: list[FileMetrics] = field(default_factory=list)
    language_breakdown: dict[str, int] = field(default_factory=dict)


class CodeMetrics:
    """Computes code metrics for a project."""

    def __init__(self, config: ArchAnalyzerConfig | None = None) -> None:
        self.config = config or ArchAnalyzerConfig()

    def analyze_file(self, file_path: str | Path) -> FileMetrics:
        """Analyze a single file and return its metrics."""
        fpath = Path(file_path)
        metrics = FileMetrics(path=str(fpath))

        if not fpath.exists() or not fpath.is_file():
            return metrics

        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return metrics

        lines = content.splitlines()
        metrics.lines_total = len(lines)

        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                metrics.lines_blank += 1
                continue

            tq = chr(34)*3  # triple double-quote
            ts = chr(39)*3  # triple single-quote
            triple_dq = stripped.count(tq)
            triple_sq = stripped.count(ts)
            if stripped.startswith(tq) or stripped.startswith(ts):
                if triple_dq >= 2 or triple_sq >= 2:
                    metrics.lines_comment += 1
                    continue
                in_docstring = not in_docstring
                metrics.lines_comment += 1
                continue

            if in_docstring:
                metrics.lines_comment += 1
                continue

            if stripped.startswith("#"):
                metrics.lines_comment += 1
            else:
                metrics.lines_code += 1

        if fpath.suffix == ".py":
            self._analyze_python_ast(content, metrics)

        return metrics

    def analyze_project(self, root: str | Path) -> ProjectMetrics:
        """Analyze all files in the project and return aggregate metrics."""
        root_path = Path(root)
        project = ProjectMetrics()

        if not root_path.exists() or not root_path.is_dir():
            return project

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in self.config.ignore_dirs]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()
                if ext in self.config.ignore_extensions:
                    continue

                file_metrics = self.analyze_file(fpath)
                project.files.append(file_metrics)
                project.total_files += 1
                project.total_lines += file_metrics.lines_total
                project.total_code_lines += file_metrics.lines_code
                project.total_comment_lines += file_metrics.lines_comment
                project.total_blank_lines += file_metrics.lines_blank
                project.total_functions += file_metrics.functions
                project.total_classes += file_metrics.classes

                lang = ext or "(no ext)"
                project.language_breakdown[lang] = (
                    project.language_breakdown.get(lang, 0) + file_metrics.lines_code
                )

        complexities = [f.complexity for f in project.files if f.complexity > 0]
        if complexities:
            project.average_complexity = round(
                sum(complexities) / len(complexities), 2
            )

        return project

    def _analyze_python_ast(self, source: str, metrics: FileMetrics) -> None:
        """Parse Python AST to extract function/class counts and complexity."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        complexity = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                metrics.functions += 1
                complexity += self._mccabe_complexity(node)
            elif isinstance(node, ast.ClassDef):
                metrics.classes += 1

        metrics.complexity = complexity

    def _mccabe_complexity(self, node: ast.AST) -> int:
        """Compute a simplified McCabe cyclomatic complexity for a function."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, (ast.Assert,)):
                complexity += 1
        return complexity
