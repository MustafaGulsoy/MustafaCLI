"""Report generator -- format analysis results as CLI tables or Markdown."""
from __future__ import annotations

from typing import Any

from .config import ArchAnalyzerConfig


class ReportGenerator:
    """Produce human-readable reports from analyzer results."""

    def __init__(self, config: ArchAnalyzerConfig) -> None:
        self._config = config

    def generate(
        self,
        structure: dict[str, Any] | None = None,
        dependencies: dict[str, Any] | None = None,
        patterns: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        api_map: dict[str, Any] | None = None,
        fmt: str = "cli",
    ) -> str:
        """Generate a combined report from all analyzer outputs.

        Args:
            structure: Output from ProjectStructureAnalyzer.
            dependencies: Output from DependencyAnalyzer.
            patterns: Output from PatternDetector.
            metrics: Output from CodeMetrics.
            api_map: Output from ApiMapper.
            fmt: Report format -- "cli" for plain text tables, "markdown" for MD.

        Returns:
            Formatted report string.
        """
        if fmt == "markdown":
            return self._markdown(structure, dependencies, patterns, metrics, api_map)
        return self._cli(structure, dependencies, patterns, metrics, api_map)

    # ------------------------------------------------------------------
    # CLI (plain text) format
    # ------------------------------------------------------------------

    def _cli(
        self,
        structure: dict[str, Any] | None,
        dependencies: dict[str, Any] | None,
        patterns: dict[str, Any] | None,
        metrics: dict[str, Any] | None,
        api_map: dict[str, Any] | None,
    ) -> str:
        sections: list[str] = []
        sections.append(self._header("Architecture Analysis Report", "="))

        if structure:
            sections.append(self._section_structure_cli(structure))
        if patterns:
            sections.append(self._section_patterns_cli(patterns))
        if metrics:
            sections.append(self._section_metrics_cli(metrics))
        if dependencies:
            sections.append(self._section_deps_cli(dependencies))
        if api_map:
            sections.append(self._section_api_cli(api_map))

        sections.append(self._summary_cli(structure, patterns, metrics, api_map))
        return "\n".join(sections)

    def _section_structure_cli(self, data: dict[str, Any]) -> str:
        lines = [self._header("Project Structure", "-")]
        lines.append(f"  Total files:       {data.get('total_files', 0)}")
        lines.append(f"  Total directories: {data.get('total_dirs', 0)}")
        techs = data.get("technologies", [])
        if techs:
            lines.append(f"  Technologies:      {', '.join(techs)}")
        fws = data.get("frameworks", [])
        if fws:
            lines.append(f"  Frameworks:        {', '.join(fws)}")
        langs = data.get("languages", {})
        if langs:
            lines.append("")
            lines.append("  Languages:")
            for lang, count in list(langs.items())[:10]:
                lines.append(f"    {lang:<25} {count:>6} files")
        eps = data.get("entry_points", [])
        if eps:
            lines.append("")
            lines.append("  Entry points:")
            for ep in eps[:10]:
                lines.append(f"    - {ep}")
        return "\n".join(lines)

    def _section_patterns_cli(self, data: dict[str, Any]) -> str:
        lines = [self._header("Architecture Patterns", "-")]
        lines.append(f"  Detected type:  {data.get('architecture_type', 'Unknown')}")
        lines.append(f"  Confidence:     {data.get('confidence', 0):.0%}")
        scores = data.get("architecture_scores", {})
        if scores:
            lines.append("")
            lines.append("  Architecture scores:")
            for arch, score in scores.items():
                bar = "#" * int(score * 20)
                lines.append(f"    {arch:<25} {score:.2f}  {bar}")
        dp = data.get("design_patterns", [])
        if dp:
            lines.append("")
            lines.append("  Design patterns found:")
            for p in dp:
                lines.append(f"    - {p}")
        infra = data.get("infrastructure_patterns", [])
        if infra:
            lines.append("")
            lines.append("  Infrastructure:")
            for p in infra:
                lines.append(f"    - {p}")
        return "\n".join(lines)

    def _section_metrics_cli(self, data: dict[str, Any]) -> str:
        lines = [self._header("Code Metrics", "-")]
        lines.append(f"  Total LOC:         {data.get('total_loc', 0):,}")
        lines.append(f"  Blank lines:       {data.get('total_blank_lines', 0):,}")
        lines.append(f"  Comment lines:     {data.get('total_comment_lines', 0):,}")
        lines.append(f"  Source files:      {data.get('total_source_files', 0):,}")
        lines.append(f"  Classes:           {data.get('total_classes', 0):,}")
        lines.append(f"  Functions:         {data.get('total_functions', 0):,}")
        lines.append(f"  Avg file size:     {data.get('avg_file_size_loc', 0):.1f} LOC")
        by_lang = data.get("by_language", {})
        if by_lang:
            lines.append("")
            lines.append(f"  {'Language':<25} {'Files':>6} {'LOC':>8} {'Comment':>8}")
            lines.append(f"  {'-'*25} {'-'*6} {'-'*8} {'-'*8}")
            for lang, stats in list(by_lang.items())[:12]:
                lines.append(
                    f"  {lang:<25} {stats['files']:>6} {stats['loc']:>8,} {stats['comment']:>8,}"
                )
        largest = data.get("largest_files", [])
        if largest:
            lines.append("")
            lines.append("  Largest files:")
            for f in largest[:10]:
                lines.append(f"    {f['loc']:>6} LOC  {f['path']}")
        return "\n".join(lines)

    def _section_deps_cli(self, data: dict[str, Any]) -> str:
        lines = [self._header("Dependencies", "-")]
        lines.append(f"  Files analyzed:        {data.get('files_analyzed', 0)}")
        lines.append(f"  Internal dep edges:    {data.get('total_internal_edges', 0)}")
        lines.append(f"  External packages:     {data.get('total_external_packages', 0)}")
        ext = data.get("external_deps", [])
        if ext:
            lines.append("")
            lines.append("  External packages:")
            for pkg in ext[:20]:
                lines.append(f"    - {pkg}")
        circular = data.get("circular_deps", [])
        if circular:
            lines.append("")
            lines.append(f"  Circular dependencies ({len(circular)} found):")
            for cycle in circular[:5]:
                lines.append(f"    {' -> '.join(cycle)}")
        else:
            lines.append("")
            lines.append("  No circular dependencies detected.")
        return "\n".join(lines)

    def _section_api_cli(self, data: dict[str, Any]) -> str:
        lines = [self._header("API Endpoints", "-")]
        lines.append(f"  Total endpoints: {data.get('total_count', 0)}")
        fws = data.get("frameworks", [])
        if fws:
            lines.append(f"  Frameworks:      {', '.join(fws)}")
        by_method = data.get("by_method", {})
        if by_method:
            lines.append("")
            lines.append("  By method:")
            for method, count in by_method.items():
                lines.append(f"    {method:<8} {count}")
        eps = data.get("endpoints", [])
        if eps:
            lines.append("")
            lines.append(f"  {'Method':<8} {'Path':<40} {'Handler':<25} {'File'}")
            lines.append(f"  {'-'*8} {'-'*40} {'-'*25} {'-'*30}")
            for ep in eps[:30]:
                lines.append(
                    f"  {ep['method']:<8} {ep['path']:<40} {ep['handler']:<25} {ep['file']}"
                )
        return "\n".join(lines)

    def _summary_cli(
        self,
        structure: dict[str, Any] | None,
        patterns: dict[str, Any] | None,
        metrics: dict[str, Any] | None,
        api_map: dict[str, Any] | None,
    ) -> str:
        lines = [self._header("Summary", "-")]
        findings: list[str] = []
        if structure:
            techs = structure.get("technologies", [])
            fws = structure.get("frameworks", [])
            if techs:
                findings.append(f"Tech stack: {', '.join(techs)}")
            if fws:
                findings.append(f"Frameworks: {', '.join(fws)}")
        if patterns:
            arch = patterns.get("architecture_type", "Unknown")
            conf = patterns.get("confidence", 0)
            findings.append(f"Architecture: {arch} (confidence: {conf:.0%})")
            dp = patterns.get("design_patterns", [])
            if dp:
                findings.append(f"Design patterns: {', '.join(dp)}")
        if metrics:
            findings.append(f"Codebase size: {metrics.get('total_loc', 0):,} LOC across {metrics.get('total_source_files', 0)} files")
        if api_map:
            count = api_map.get("total_count", 0)
            if count:
                findings.append(f"API surface: {count} endpoints")

        if findings:
            for f in findings:
                lines.append(f"  - {f}")
        else:
            lines.append("  No significant findings.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Markdown format
    # ------------------------------------------------------------------

    def _markdown(
        self,
        structure: dict[str, Any] | None,
        dependencies: dict[str, Any] | None,
        patterns: dict[str, Any] | None,
        metrics: dict[str, Any] | None,
        api_map: dict[str, Any] | None,
    ) -> str:
        lines: list[str] = ["# Architecture Analysis Report", ""]

        if structure:
            lines.append("## Project Structure")
            lines.append(f"- **Total files:** {structure.get('total_files', 0)}")
            lines.append(f"- **Total directories:** {structure.get('total_dirs', 0)}")
            techs = structure.get("technologies", [])
            if techs:
                lines.append(f"- **Technologies:** {', '.join(techs)}")
            fws = structure.get("frameworks", [])
            if fws:
                lines.append(f"- **Frameworks:** {', '.join(fws)}")
            langs = structure.get("languages", {})
            if langs:
                lines.append("")
                lines.append("| Language | Files |")
                lines.append("|----------|------:|")
                for lang, count in list(langs.items())[:10]:
                    lines.append(f"| {lang} | {count} |")
            lines.append("")

        if patterns:
            lines.append("## Architecture Patterns")
            lines.append(f"- **Type:** {patterns.get('architecture_type', 'Unknown')}")
            lines.append(f"- **Confidence:** {patterns.get('confidence', 0):.0%}")
            dp = patterns.get("design_patterns", [])
            if dp:
                lines.append(f"- **Design patterns:** {', '.join(dp)}")
            infra = patterns.get("infrastructure_patterns", [])
            if infra:
                lines.append(f"- **Infrastructure:** {', '.join(infra)}")
            lines.append("")

        if metrics:
            lines.append("## Code Metrics")
            lines.append(f"- **Total LOC:** {metrics.get('total_loc', 0):,}")
            lines.append(f"- **Source files:** {metrics.get('total_source_files', 0):,}")
            lines.append(f"- **Classes:** {metrics.get('total_classes', 0):,}")
            lines.append(f"- **Functions:** {metrics.get('total_functions', 0):,}")
            lines.append(f"- **Avg file size:** {metrics.get('avg_file_size_loc', 0):.1f} LOC")
            lines.append("")

        if dependencies:
            lines.append("## Dependencies")
            lines.append(f"- **Internal edges:** {dependencies.get('total_internal_edges', 0)}")
            lines.append(f"- **External packages:** {dependencies.get('total_external_packages', 0)}")
            circular = dependencies.get("circular_deps", [])
            if circular:
                lines.append(f"- **Circular dependencies:** {len(circular)} found")
            lines.append("")

        if api_map and api_map.get("total_count", 0) > 0:
            lines.append("## API Endpoints")
            lines.append(f"- **Total:** {api_map['total_count']}")
            fws = api_map.get("frameworks", [])
            if fws:
                lines.append(f"- **Frameworks:** {', '.join(fws)}")
            eps = api_map.get("endpoints", [])
            if eps:
                lines.append("")
                lines.append("| Method | Path | Handler | File |")
                lines.append("|--------|------|---------|------|")
                for ep in eps[:30]:
                    lines.append(
                        f"| {ep['method']} | `{ep['path']}` | {ep['handler']} | {ep['file']} |"
                    )
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _header(title: str, char: str = "=") -> str:
        width = max(len(title) + 4, 60)
        return f"\n{char * width}\n  {title}\n{char * width}"
