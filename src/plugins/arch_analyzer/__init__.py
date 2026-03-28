"""Arch-Analyzer: Project architecture analysis plugin."""
from .plugin import ArchAnalyzerPlugin

__all__ = ["ArchAnalyzerPlugin"]


def register(registry):
    """Register arch-analyzer plugin with MustafaCLI plugin registry."""
    registry.register(ArchAnalyzerPlugin)
