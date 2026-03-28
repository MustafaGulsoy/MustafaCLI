"""Project structure analyzer - directory tree and tech stack detection."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ArchAnalyzerConfig


@dataclass
class FileInfo:
    """Information about a single file."""

    path: str
    extension: str
    size: int
    lines: int = 0


@dataclass
class DirectoryNode:
    """A node in the directory tree."""

    name: str
    path: str
    children: list[DirectoryNode] = field(default_factory=list)
    files: list[FileInfo] = field(default_factory=list)
    depth: int = 0


@dataclass
class TechStack:
    """Detected technology stack."""

    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    build_tools: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)


# Mapping of marker files/dirs to tech stack entries
_FRAMEWORK_MARKERS: dict[str, dict[str, str]] = {
    "requirements.txt": {"package_managers": "pip"},
    "pyproject.toml": {"build_tools": "pyproject"},
    "setup.py": {"build_tools": "setuptools"},
    "Pipfile": {"package_managers": "pipenv"},
    "poetry.lock": {"package_managers": "poetry"},
    "package.json": {"package_managers": "npm"},
    "yarn.lock": {"package_managers": "yarn"},
    "pnpm-lock.yaml": {"package_managers": "pnpm"},
    "Cargo.toml": {"build_tools": "cargo", "package_managers": "cargo"},
    "go.mod": {"build_tools": "go", "package_managers": "go modules"},
    "Makefile": {"build_tools": "make"},
    "CMakeLists.txt": {"build_tools": "cmake"},
    "Dockerfile": {"build_tools": "docker"},
    "docker-compose.yml": {"build_tools": "docker-compose"},
    "docker-compose.yaml": {"build_tools": "docker-compose"},
}

_LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript (React)",
    ".tsx": "TypeScript (React)",
    ".java": "Java",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".dart": "Dart",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
}

_FRAMEWORK_CONTENT_MARKERS: dict[str, list[tuple[str, str]]] = {
    ".py": [
        ("flask", "Flask"),
        ("fastapi", "FastAPI"),
        ("django", "Django"),
        ("tornado", "Tornado"),
        ("starlette", "Starlette"),
    ],
    ".js": [
        ("express", "Express"),
        ("react", "React"),
        ("vue", "Vue"),
        ("angular", "Angular"),
        ("next", "Next.js"),
    ],
    ".ts": [
        ("express", "Express"),
        ("nestjs", "NestJS"),
        ("angular", "Angular"),
    ],
    ".cs": [
        ("Microsoft.AspNetCore", "ASP.NET Core"),
        ("Microsoft.EntityFrameworkCore", "Entity Framework Core"),
    ],
}


class ProjectStructureAnalyzer:
    """Analyzes project directory structure and detects technology stack."""

    def __init__(self, config: ArchAnalyzerConfig | None = None) -> None:
        self.config = config or ArchAnalyzerConfig()

    def build_tree(self, root: str | Path) -> DirectoryNode:
        """Build a directory tree from the given root path."""
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(f"Path does not exist: {root}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root}")
        return self._walk(root_path, depth=0)

    def _walk(self, path: Path, depth: int) -> DirectoryNode:
        """Recursively walk directory to build tree."""
        node = DirectoryNode(
            name=path.name or str(path),
            path=str(path),
            depth=depth,
        )
        if depth >= self.config.max_depth:
            return node

        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return node

        file_count = 0
        for entry in entries:
            if entry.is_dir():
                if entry.name in self.config.ignore_dirs:
                    continue
                child = self._walk(entry, depth + 1)
                node.children.append(child)
            elif entry.is_file():
                ext = entry.suffix.lower()
                if ext in self.config.ignore_extensions:
                    continue
                file_count += 1
                if file_count > self.config.max_files:
                    break
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                lines = self._count_lines(entry)
                node.files.append(
                    FileInfo(
                        path=str(entry),
                        extension=ext,
                        size=size,
                        lines=lines,
                    )
                )
        return node

    def _count_lines(self, path: Path) -> int:
        """Count lines in a text file. Returns 0 for binary/unreadable files."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return sum(1 for _ in f)
        except (OSError, UnicodeDecodeError):
            return 0

    def detect_tech_stack(self, root: str | Path) -> TechStack:
        """Detect technology stack from project files."""
        root_path = Path(root)
        stack = TechStack()
        if not root_path.exists() or not root_path.is_dir():
            return stack

        seen_languages: set[str] = set()
        seen_frameworks: set[str] = set()

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune ignored dirs
            dirnames[:] = [d for d in dirnames if d not in self.config.ignore_dirs]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()

                # Language detection
                if ext in _LANGUAGE_EXTENSIONS:
                    lang = _LANGUAGE_EXTENSIONS[ext]
                    if lang not in seen_languages:
                        seen_languages.add(lang)
                        stack.languages.append(lang)

                # Marker file detection
                if fname in _FRAMEWORK_MARKERS:
                    marker = _FRAMEWORK_MARKERS[fname]
                    for category, value in marker.items():
                        target_list = getattr(stack, category)
                        if value not in target_list:
                            target_list.append(value)

                # Content-based framework detection
                if ext in _FRAMEWORK_CONTENT_MARKERS:
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore").lower()
                    except OSError:
                        continue
                    for keyword, fw_name in _FRAMEWORK_CONTENT_MARKERS[ext]:
                        if keyword in content and fw_name not in seen_frameworks:
                            seen_frameworks.add(fw_name)
                            stack.frameworks.append(fw_name)

                # .csproj detection
                if ext == ".csproj":
                    if "C#" not in seen_languages:
                        seen_languages.add("C#")
                        stack.languages.append("C#")
                    if "msbuild" not in stack.build_tools:
                        stack.build_tools.append("msbuild")

        return stack

    def get_file_stats(self, tree: DirectoryNode) -> dict[str, Any]:
        """Compute aggregate file statistics from a directory tree."""
        ext_counts: dict[str, int] = {}
        totals: dict[str, int] = {"files": 0, "lines": 0, "size": 0}
        self._aggregate_stats(tree, ext_counts, totals)
        return {
            "total_files": totals["files"],
            "total_lines": totals["lines"],
            "total_size_bytes": totals["size"],
            "extensions": ext_counts,
        }

    def _aggregate_stats(
        self,
        node: DirectoryNode,
        ext_counts: dict[str, int],
        totals: dict[str, int],
    ) -> None:
        """Recursively aggregate file statistics."""
        for f in node.files:
            ext = f.extension or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            totals["files"] += 1
            totals["lines"] += f.lines
            totals["size"] += f.size
        for child in node.children:
            self._aggregate_stats(child, ext_counts, totals)
