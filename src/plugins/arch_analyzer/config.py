"""Arch-Analyzer configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ArchAnalyzerConfig:
    """Configuration for the arch-analyzer plugin."""

    max_depth: int = 8
    max_files: int = 5000
    ignore_dirs: list[str] = field(
        default_factory=lambda: [
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".tox",
            "dist",
            "build",
            ".eggs",
            "bin",
            "obj",
        ]
    )
    ignore_extensions: list[str] = field(
        default_factory=lambda: [
            ".pyc",
            ".pyo",
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".class",
            ".o",
            ".obj",
        ]
    )
    report_format: str = "markdown"  # markdown | cli | json

    @classmethod
    def from_env(cls) -> ArchAnalyzerConfig:
        """Load configuration from environment variables."""
        ignore_dirs_env = os.getenv("ARCH_ANALYZER_IGNORE_DIRS", "")
        ignore_dirs = (
            ignore_dirs_env.split(",")
            if ignore_dirs_env
            else cls.__dataclass_fields__["ignore_dirs"].default_factory()
        )
        return cls(
            max_depth=int(os.getenv("ARCH_ANALYZER_MAX_DEPTH", "8")),
            max_files=int(os.getenv("ARCH_ANALYZER_MAX_FILES", "5000")),
            ignore_dirs=ignore_dirs,
            report_format=os.getenv("ARCH_ANALYZER_REPORT_FORMAT", "markdown"),
        )
