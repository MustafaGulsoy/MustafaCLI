"""Pattern detector - architectural pattern recognition."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ArchAnalyzerConfig


@dataclass
class PatternMatch:
    """A detected architectural pattern."""

    name: str
    confidence: float  # 0.0 to 1.0
    evidence: list[str] = field(default_factory=list)
    description: str = ""


_PATTERN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "MVC": {
        "dir_markers": ["models", "views", "controllers"],
        "description": "Model-View-Controller pattern",
        "min_markers": 3,
    },
    "Layered": {
        "dir_markers": ["domain", "application", "infrastructure", "presentation"],
        "alt_markers": ["core", "services", "repositories", "api"],
        "description": "Layered / N-Tier architecture",
        "min_markers": 3,
    },
    "Hexagonal": {
        "dir_markers": ["domain", "ports", "adapters"],
        "alt_markers": ["core", "inbound", "outbound"],
        "description": "Hexagonal / Ports & Adapters architecture",
        "min_markers": 2,
    },
    "Clean Architecture": {
        "dir_markers": ["entities", "use_cases", "interfaces", "frameworks"],
        "alt_markers": ["domain", "application", "infrastructure", "presentation"],
        "description": "Clean Architecture (Uncle Bob)",
        "min_markers": 3,
    },
    "CQRS": {
        "dir_markers": ["commands", "queries"],
        "alt_markers": ["command_handlers", "query_handlers"],
        "description": "Command Query Responsibility Segregation",
        "min_markers": 2,
    },
    "Microservices": {
        "dir_markers": ["services"],
        "file_markers": ["docker-compose.yml", "docker-compose.yaml"],
        "description": "Microservices architecture",
        "min_markers": 2,
    },
    "Repository Pattern": {
        "dir_markers": ["repositories"],
        "alt_markers": ["repos", "data"],
        "description": "Repository pattern for data access",
        "min_markers": 1,
    },
    "Feature-based": {
        "dir_markers": ["features"],
        "alt_markers": ["modules"],
        "description": "Feature-based / Modular architecture",
        "min_markers": 1,
    },
}


class PatternDetector:
    """Detects architectural patterns in project directory structures."""

    def __init__(self, config: ArchAnalyzerConfig | None = None) -> None:
        self.config = config or ArchAnalyzerConfig()

    def detect_patterns(self, root: str | Path) -> list[PatternMatch]:
        """Scan the project and return detected architectural patterns."""
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            return []

        dir_names = self._collect_dir_names(root_path)
        file_names = self._collect_root_files(root_path)
        matches: list[PatternMatch] = []

        for pattern_name, definition in _PATTERN_DEFINITIONS.items():
            match = self._check_pattern(pattern_name, definition, dir_names, file_names)
            if match is not None:
                matches.append(match)

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def detect_single_pattern(self, root: str | Path, pattern_name: str) -> PatternMatch | None:
        """Check for a specific pattern by name."""
        if pattern_name not in _PATTERN_DEFINITIONS:
            return None

        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            return None

        dir_names = self._collect_dir_names(root_path)
        file_names = self._collect_root_files(root_path)
        definition = _PATTERN_DEFINITIONS[pattern_name]
        return self._check_pattern(pattern_name, definition, dir_names, file_names)

    def get_supported_patterns(self) -> list[str]:
        """Return list of all patterns that can be detected."""
        return list(_PATTERN_DEFINITIONS.keys())

    def _check_pattern(
        self,
        name: str,
        definition: dict[str, Any],
        dir_names: set[str],
        file_names: set[str],
    ) -> PatternMatch | None:
        """Check whether a pattern matches the project structure."""
        evidence: list[str] = []
        total_possible = 0
        matched = 0

        primary_markers = definition.get("dir_markers", [])
        total_possible += len(primary_markers)
        for marker in primary_markers:
            if marker in dir_names:
                matched += 1
                evidence.append(f"directory: {marker}/")

        alt_markers = definition.get("alt_markers", [])
        if alt_markers:
            total_possible += len(alt_markers)
            for marker in alt_markers:
                if marker in dir_names:
                    matched += 1
                    evidence.append(f"directory: {marker}/")

        file_markers = definition.get("file_markers", [])
        if file_markers:
            total_possible += len(file_markers)
            for marker in file_markers:
                if marker in file_names:
                    matched += 1
                    evidence.append(f"file: {marker}")

        min_markers = definition.get("min_markers", 2)
        if matched < min_markers:
            return None

        confidence = matched / total_possible if total_possible > 0 else 0.0
        return PatternMatch(
            name=name,
            confidence=round(confidence, 2),
            evidence=evidence,
            description=definition.get("description", ""),
        )

    def _collect_dir_names(self, root: Path) -> set[str]:
        """Collect all directory names (lowercased) up to max_depth."""
        names: set[str] = set()
        self._walk_dirs(root, names, depth=0)
        return names

    def _walk_dirs(self, path: Path, names: set[str], depth: int) -> None:
        """Recursively collect directory names."""
        if depth >= self.config.max_depth:
            return
        try:
            for entry in path.iterdir():
                if entry.is_dir() and entry.name not in self.config.ignore_dirs:
                    names.add(entry.name.lower())
                    self._walk_dirs(entry, names, depth + 1)
        except PermissionError:
            pass

    def _collect_root_files(self, root: Path) -> set[str]:
        """Collect file names in the root directory."""
        names: set[str] = set()
        try:
            for entry in root.iterdir():
                if entry.is_file():
                    names.add(entry.name)
        except PermissionError:
            pass
        return names
