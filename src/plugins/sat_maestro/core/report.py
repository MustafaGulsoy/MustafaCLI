"""Report generator for SAT-MAESTRO analysis results."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from ..config import SatMaestroConfig

logger = logging.getLogger(__name__)


class ReportFormat(str, Enum):
    CLI = "cli"
    JSON = "json"
    HTML = "html"
    NEO4J = "neo4j"
    ALL = "all"


class ReportGenerator:
    """Generate analysis reports in multiple formats."""

    def __init__(self, config: SatMaestroConfig) -> None:
        self._config = config

    async def generate(
        self,
        results: list[AnalysisResult],
        fmt: ReportFormat | str = ReportFormat.CLI,
        output_dir: str | None = None,
        run_id: str | None = None,
    ) -> str:
        """Generate report in the specified format. Returns report content or file path."""
        if isinstance(fmt, str):
            fmt = ReportFormat(fmt)

        out_dir = Path(output_dir or self._config.report_output_dir)
        rid = run_id or datetime.now().strftime("%Y-%m-%d-%H%M%S")

        if fmt == ReportFormat.ALL:
            paths = []
            for f in [ReportFormat.CLI, ReportFormat.JSON, ReportFormat.HTML]:
                p = await self.generate(results, f, str(out_dir), rid)
                paths.append(p)
            return "\n".join(paths)

        if fmt == ReportFormat.CLI:
            return self._render_cli(results, rid)
        elif fmt == ReportFormat.JSON:
            return self._render_json(results, rid, out_dir)
        elif fmt == ReportFormat.HTML:
            return self._render_html(results, rid, out_dir)
        elif fmt == ReportFormat.NEO4J:
            return f"Results stored in Neo4j. View at http://localhost:7474 (run: {rid})"

        return ""

    def _render_cli(self, results: list[AnalysisResult], run_id: str) -> str:
        """Render CLI text report with colored status indicators."""
        lines = []
        overall = self._overall_status(results)
        status_icon = {"PASS": "✅", "WARN": "⚠", "FAIL": "❌"}

        lines.append("╭─────────────────── SAT-MAESTRO Analysis Report ───────────────────╮")
        lines.append(f"│ Run: #{run_id} │ Status: {status_icon.get(overall.value, '?')} {overall.value:<30}│")
        lines.append("├───────────────────────────────────────────────────────────────────┤")

        for r in results:
            icon = status_icon.get(r.status.value, "?")
            summary_text = self._summarize_result(r)
            analyzer_name = r.analyzer.replace("_", " ").title()
            lines.append(f"│ {analyzer_name:<28} {icon} {r.status.value:<6} {summary_text:<25}│")

        lines.append("╰───────────────────────────────────────────────────────────────────╯")

        # List violations
        all_violations = []
        for r in results:
            all_violations.extend(r.violations)

        if all_violations:
            lines.append("")
            lines.append("Violations:")
            for v in sorted(all_violations, key=lambda x: x.severity.value):
                icon = "❌" if v.severity == Severity.ERROR else "⚠" if v.severity == Severity.WARNING else "ℹ"
                lines.append(f" {icon}  {v.rule_id:<24} {v.message}")

        return "\n".join(lines)

    def _render_json(self, results: list[AnalysisResult], run_id: str, out_dir: Path) -> str:
        """Render JSON report and save to file."""
        overall = self._overall_status(results)

        report = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "status": overall.value,
            "analyzers": {},
            "violations": [],
            "exit_code": 0 if overall == AnalysisStatus.PASS else 1,
        }

        for r in results:
            report["analyzers"][r.analyzer] = {
                "status": r.status.value,
                "violations": len(r.violations),
                "summary": r.summary,
            }
            for v in r.violations:
                report["violations"].append({
                    "rule_id": v.rule_id,
                    "severity": v.severity.value,
                    "message": v.message,
                    "component_path": v.component_path,
                    "details": v.details,
                })

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"sat-maestro-{run_id}.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        logger.info("JSON report saved to %s", path)
        return str(path)

    def _render_html(self, results: list[AnalysisResult], run_id: str, out_dir: Path) -> str:
        """Render HTML report and save to file."""
        overall = self._overall_status(results)
        all_violations = []
        for r in results:
            all_violations.extend(r.violations)

        # Try Jinja2, fall back to basic HTML
        try:
            return self._render_html_jinja(results, run_id, out_dir, overall, all_violations)
        except ImportError:
            return self._render_html_basic(results, run_id, out_dir, overall, all_violations)

    def _render_html_jinja(
        self, results: list[AnalysisResult], run_id: str, out_dir: Path,
        overall: AnalysisStatus, violations: list[Violation]
    ) -> str:
        """Render HTML using Jinja2 template."""
        from jinja2 import Environment, FileSystemLoader

        template_dir = Path(__file__).parent.parent / "templates"
        if not (template_dir / "report.html").exists():
            return self._render_html_basic(results, run_id, out_dir, overall, violations)

        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        template = env.get_template("report.html")

        html = template.render(
            run_id=run_id,
            timestamp=datetime.now().isoformat(),
            overall_status=overall.value,
            results=results,
            violations=violations,
            Severity=Severity,
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"sat-maestro-{run_id}.html"
        path.write_text(html, encoding="utf-8")
        logger.info("HTML report saved to %s", path)
        return str(path)

    def _render_html_basic(
        self, results: list[AnalysisResult], run_id: str, out_dir: Path,
        overall: AnalysisStatus, violations: list[Violation]
    ) -> str:
        """Render basic HTML without Jinja2."""
        status_colors = {"PASS": "#22c55e", "WARN": "#f59e0b", "FAIL": "#ef4444"}

        analyzer_rows = ""
        for r in results:
            color = status_colors.get(r.status.value, "#888")
            analyzer_rows += f"""
            <tr>
                <td>{r.analyzer.replace('_', ' ').title()}</td>
                <td style="color:{color};font-weight:bold">{r.status.value}</td>
                <td>{len(r.violations)}</td>
                <td>{self._summarize_result(r)}</td>
            </tr>"""

        violation_rows = ""
        for v in violations:
            sev_color = status_colors.get(
                "FAIL" if v.severity == Severity.ERROR else "WARN" if v.severity == Severity.WARNING else "PASS",
                "#888"
            )
            violation_rows += f"""
            <tr>
                <td style="color:{sev_color}">{v.severity.value}</td>
                <td><code>{v.rule_id}</code></td>
                <td>{v.message}</td>
                <td><code>{v.component_path}</code></td>
            </tr>"""

        overall_color = status_colors.get(overall.value, "#888")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SAT-MAESTRO Report #{run_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #f8fafc; margin-bottom: 0.5rem; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; padding: 1.5rem; background: #1e293b; border-radius: 12px; border-left: 4px solid {overall_color}; }}
        .status {{ font-size: 1.5rem; font-weight: bold; color: {overall_color}; }}
        .meta {{ color: #94a3b8; font-size: 0.875rem; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
        th {{ background: #1e293b; padding: 0.75rem 1rem; text-align: left; color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
        td {{ padding: 0.75rem 1rem; border-bottom: 1px solid #1e293b; }}
        tr:hover {{ background: #1e293b40; }}
        .section {{ margin-bottom: 2rem; }}
        .section h2 {{ color: #f8fafc; margin-bottom: 1rem; font-size: 1.25rem; }}
        code {{ background: #1e293b; padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.875rem; }}
        .footer {{ text-align: center; color: #475569; font-size: 0.75rem; margin-top: 3rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>SAT-MAESTRO Analysis Report</h1>
                <div class="meta">Run #{run_id} &bull; {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            <div class="status">{overall.value}</div>
        </div>

        <div class="section">
            <h2>Analyzer Results</h2>
            <table>
                <thead><tr><th>Analyzer</th><th>Status</th><th>Violations</th><th>Summary</th></tr></thead>
                <tbody>{analyzer_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <h2>Violations ({len(violations)})</h2>
            <table>
                <thead><tr><th>Severity</th><th>Rule</th><th>Message</th><th>Component</th></tr></thead>
                <tbody>{violation_rows if violation_rows else '<tr><td colspan="4" style="text-align:center;color:#22c55e">No violations found</td></tr>'}</tbody>
            </table>
        </div>

        <div class="footer">
            Generated by SAT-MAESTRO &bull; Kardelen Yazilim
        </div>
    </div>
</body>
</html>"""

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"sat-maestro-{run_id}.html"
        path.write_text(html, encoding="utf-8")
        logger.info("HTML report saved to %s", path)
        return str(path)

    @staticmethod
    def _overall_status(results: list[AnalysisResult]) -> AnalysisStatus:
        """Determine overall status from individual results."""
        if any(r.status == AnalysisStatus.FAIL for r in results):
            return AnalysisStatus.FAIL
        if any(r.status == AnalysisStatus.WARN for r in results):
            return AnalysisStatus.WARN
        return AnalysisStatus.PASS

    @staticmethod
    def _summarize_result(r: AnalysisResult) -> str:
        """Create a short summary string for an analysis result."""
        s = r.summary
        if r.analyzer == "pin_to_pin":
            checked = s.get("connections_checked", 0)
            opens = s.get("open_circuits", 0)
            return f"{checked - opens}/{checked} verified"
        elif r.analyzer == "power_budget":
            rails = s.get("rails_analyzed", 0)
            margin_pct = s.get("overall_margin", 0)
            return f"{rails} rails, {margin_pct:.0%} margin"
        elif r.analyzer == "connector":
            pairs = s.get("mate_pairs", 0)
            return f"{pairs} pairs checked"
        return f"{len(r.violations)} issues"
