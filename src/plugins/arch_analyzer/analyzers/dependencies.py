"""Dependency analyzer - import graph and circular dependency detection."""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ArchAnalyzerConfig


@dataclass
class ImportInfo:
    """A single import statement."""

    module: str
    names: list[str] = field(default_factory=list)
    is_relative: bool = False
    source_file: str = ""
    line_number: int = 0


@dataclass
class DependencyGraph:
    """Directed graph of module dependencies."""

    nodes: set[str] = field(default_factory=set)
    edges: list[tuple[str, str]] = field(default_factory=list)
    imports: dict[str, list[ImportInfo]] = field(default_factory=dict)

    def add_edge(self, source: str, target: str) -> None:
        """Add a dependency edge from source to target."""
        self.nodes.add(source)
        self.nodes.add(target)
        self.edges.append((source, target))

    def get_dependencies(self, module: str) -> list[str]:
        """Get all modules that the given module depends on."""
        return [target for source, target in self.edges if source == module]

    def get_dependents(self, module: str) -> list[str]:
        """Get all modules that depend on the given module."""
        return [source for source, target in self.edges if target == module]


class DependencyAnalyzer:
    """Analyzes project dependencies by parsing import statements."""

    def __init__(self, config: ArchAnalyzerConfig | None = None) -> None:
        self.config = config or ArchAnalyzerConfig()

    def build_import_graph(self, root: str | Path) -> DependencyGraph:
        """Build a dependency graph from Python imports in the project."""
        root_path = Path(root)
        graph = DependencyGraph()

        if not root_path.exists() or not root_path.is_dir():
            return graph

        py_files = list(root_path.rglob("*.py"))
        for py_file in py_files:
            if any(part in self.config.ignore_dirs for part in py_file.parts):
                continue
            module_name = self._path_to_module(py_file, root_path)
            imports = self._extract_imports(py_file)
            graph.imports[module_name] = imports
            graph.nodes.add(module_name)

            for imp in imports:
                resolved = self._resolve_import(imp, module_name, root_path)
                if resolved:
                    graph.add_edge(module_name, resolved)

        return graph

    def build_js_import_graph(self, root: str | Path) -> DependencyGraph:
        """Build a dependency graph from JavaScript/TypeScript imports."""
        root_path = Path(root)
        graph = DependencyGraph()

        if not root_path.exists() or not root_path.is_dir():
            return graph

        patterns = ["*.js", "*.ts", "*.jsx", "*.tsx"]
        for pattern in patterns:
            for js_file in root_path.rglob(pattern):
                if any(part in self.config.ignore_dirs for part in js_file.parts):
                    continue
                module_name = str(js_file.relative_to(root_path))
                imports = self._extract_js_imports(js_file)
                graph.imports[module_name] = imports
                graph.nodes.add(module_name)

                for imp in imports:
                    graph.add_edge(module_name, imp.module)

        return graph

    def find_circular_dependencies(self, graph: DependencyGraph) -> list[list[str]]:
        """Find all circular dependency chains in the graph."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        adjacency: dict[str, list[str]] = {}
        for src, tgt in graph.edges:
            adjacency.setdefault(src, []).append(tgt)

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for node in sorted(graph.nodes):
            if node not in visited:
                dfs(node, [])

        return cycles

    def get_external_dependencies(self, graph: DependencyGraph) -> list[str]:
        """Return list of external (third-party) module names."""
        internal_modules = graph.nodes
        external: set[str] = set()

        for imports_list in graph.imports.values():
            for imp in imports_list:
                if not imp.is_relative:
                    top_level = imp.module.split(".")[0]
                    if top_level not in internal_modules and not self._is_stdlib(top_level):
                        external.add(top_level)

        return sorted(external)

    def parse_package_json(self, root: str | Path) -> dict[str, Any]:
        """Parse package.json for declared dependencies."""
        pkg_path = Path(root) / "package.json"
        if not pkg_path.exists():
            return {}
        try:
            data = json.loads(pkg_path.read_text(encoding="utf-8"))
            return {
                "dependencies": data.get("dependencies", {}),
                "devDependencies": data.get("devDependencies", {}),
            }
        except (json.JSONDecodeError, OSError):
            return {}

    def _extract_imports(self, file_path: Path) -> list[ImportInfo]:
        """Extract import statements from a Python file using AST."""
        imports: list[ImportInfo] = []
        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError):
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportInfo(
                            module=alias.name,
                            names=[alias.asname or alias.name],
                            is_relative=False,
                            source_file=str(file_path),
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                is_relative = (node.level or 0) > 0
                names = [alias.name for alias in node.names]
                imports.append(
                    ImportInfo(
                        module=module,
                        names=names,
                        is_relative=is_relative,
                        source_file=str(file_path),
                        line_number=node.lineno,
                    )
                )

        return imports

    def _extract_js_imports(self, file_path: Path) -> list[ImportInfo]:
        """Extract import/require statements from JavaScript/TypeScript files."""
        imports: list[ImportInfo] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return imports

        es6_pattern = re.compile(r"import\s+.*?from\s+['\"](.*?)['\"]", re.MULTILINE)
        for match in es6_pattern.finditer(content):
            module = match.group(1)
            imports.append(
                ImportInfo(
                    module=module,
                    is_relative=module.startswith("."),
                    source_file=str(file_path),
                )
            )

        cjs_pattern = re.compile(r"require\s*\(\s*['\"](.*?)['\"]\s*\)", re.MULTILINE)
        for match in cjs_pattern.finditer(content):
            module = match.group(1)
            imports.append(
                ImportInfo(
                    module=module,
                    is_relative=module.startswith("."),
                    source_file=str(file_path),
                )
            )

        return imports

    def _path_to_module(self, file_path: Path, root: Path) -> str:
        """Convert a file path to a Python module name."""
        rel = file_path.relative_to(root)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].rsplit(".", 1)[0]
        return ".".join(parts)

    def _resolve_import(
        self, imp: ImportInfo, source_module: str, root: Path
    ) -> str | None:
        """Try to resolve an import to an internal module name."""
        if imp.is_relative:
            parts = source_module.split(".")
            if parts:
                parent = ".".join(parts[:-1])
                resolved = f"{parent}.{imp.module}" if imp.module else parent
                return resolved
            return None

        module_path = root / Path(*imp.module.split("."))
        if module_path.with_suffix(".py").exists() or (module_path / "__init__.py").exists():
            return imp.module

        return None

    def _is_stdlib(self, module_name: str) -> bool:
        """Check if a module is part of the Python standard library."""
        _STDLIB = {
            "os", "sys", "re", "json", "ast", "math", "pathlib", "typing",
            "collections", "functools", "itertools", "datetime", "logging",
            "unittest", "abc", "io", "hashlib", "subprocess", "shutil",
            "tempfile", "dataclasses", "enum", "contextlib", "copy",
            "importlib", "inspect", "textwrap", "argparse", "configparser",
            "csv", "sqlite3", "http", "urllib", "email", "html", "xml",
            "socket", "threading", "multiprocessing", "asyncio", "concurrent",
            "ctypes", "struct", "array", "queue", "heapq", "bisect",
            "statistics", "random", "secrets", "string", "pprint",
            "warnings", "traceback", "dis", "pickle", "shelve", "dbm",
            "gzip", "bz2", "zipfile", "tarfile", "glob", "fnmatch",
            "time", "calendar", "locale", "gettext", "signal", "mmap",
            "codecs", "unicodedata", "pdb", "profile", "timeit", "gc",
            "weakref", "operator", "decimal", "fractions", "numbers",
        }
        return module_name in _STDLIB
