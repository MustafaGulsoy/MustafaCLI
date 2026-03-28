"""Tests for PatternDetector."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig
from src.plugins.arch_analyzer.analyzers.patterns import PatternDetector, PatternMatch


class TestDetectPatterns:
    """Tests for PatternDetector.detect_patterns."""

    def test_mvc_detected_in_mvc_project(self, mvc_project: Path) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns(mvc_project)
        pattern_names = [p.name for p in patterns]
        assert "MVC" in pattern_names

    def test_mvc_confidence_is_high(self, mvc_project: Path) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns(mvc_project)
        mvc = next(p for p in patterns if p.name == "MVC")
        assert mvc.confidence >= 0.8

    def test_mvc_has_evidence(self, mvc_project: Path) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns(mvc_project)
        mvc = next(p for p in patterns if p.name == "MVC")
        assert len(mvc.evidence) >= 3
        evidence_str = " ".join(mvc.evidence)
        assert "models" in evidence_str
        assert "views" in evidence_str
        assert "controllers" in evidence_str

    def test_cqrs_detected(self, cqrs_project: Path) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns(cqrs_project)
        pattern_names = [p.name for p in patterns]
        assert "CQRS" in pattern_names

    def test_patterns_sorted_by_confidence(self, mvc_project: Path) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns(mvc_project)
        if len(patterns) > 1:
            for i in range(len(patterns) - 1):
                assert patterns[i].confidence >= patterns[i + 1].confidence

    def test_empty_project_no_patterns(self, empty_project: Path) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns(empty_project)
        assert patterns == []

    def test_nonexistent_dir_no_patterns(self) -> None:
        detector = PatternDetector()
        patterns = detector.detect_patterns("/nonexistent/path/xyz")
        assert patterns == []

    def test_repository_pattern_detected(self, tmp_path: Path) -> None:
        """Project with repositories/ dir should detect Repository Pattern."""
        root = tmp_path / "repo_project"
        root.mkdir()
        (root / "repositories").mkdir()
        (root / "repositories" / "__init__.py").write_text("")

        detector = PatternDetector()
        patterns = detector.detect_patterns(root)
        pattern_names = [p.name for p in patterns]
        assert "Repository Pattern" in pattern_names

    def test_feature_based_detected(self, tmp_path: Path) -> None:
        """Project with features/ dir should detect Feature-based pattern."""
        root = tmp_path / "feat_project"
        root.mkdir()
        (root / "features").mkdir()
        (root / "features" / "__init__.py").write_text("")

        detector = PatternDetector()
        patterns = detector.detect_patterns(root)
        pattern_names = [p.name for p in patterns]
        assert "Feature-based" in pattern_names


class TestDetectSinglePattern:
    """Tests for PatternDetector.detect_single_pattern."""

    def test_specific_mvc_check(self, mvc_project: Path) -> None:
        detector = PatternDetector()
        match = detector.detect_single_pattern(mvc_project, "MVC")
        assert match is not None
        assert match.name == "MVC"

    def test_specific_pattern_not_found(self, empty_project: Path) -> None:
        detector = PatternDetector()
        match = detector.detect_single_pattern(empty_project, "MVC")
        assert match is None

    def test_unknown_pattern_name(self, mvc_project: Path) -> None:
        detector = PatternDetector()
        match = detector.detect_single_pattern(mvc_project, "NonexistentPattern")
        assert match is None


class TestGetSupportedPatterns:
    """Tests for PatternDetector.get_supported_patterns."""

    def test_returns_pattern_names(self) -> None:
        detector = PatternDetector()
        patterns = detector.get_supported_patterns()
        assert "MVC" in patterns
        assert "CQRS" in patterns
        assert "Layered" in patterns
        assert len(patterns) >= 5

    def test_returns_list(self) -> None:
        detector = PatternDetector()
        patterns = detector.get_supported_patterns()
        assert isinstance(patterns, list)
