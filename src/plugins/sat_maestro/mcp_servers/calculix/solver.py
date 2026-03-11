"""CalculiX CLI wrapper for running FEM analyses."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from .result_parser import CalculixResultParser

logger = logging.getLogger(__name__)


class CalculixSolver:
    """Wrapper around CalculiX (ccx) command-line solver."""

    def __init__(self, ccx_path: str | None = None) -> None:
        self._ccx = ccx_path or shutil.which("ccx") or "ccx"
        self._parser = CalculixResultParser()

    async def solve(self, input_file: str, num_cpus: int = 1) -> dict[str, Any]:
        """Run CalculiX solver on input file."""
        inp_path = Path(input_file)
        if not inp_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        job_name = inp_path.stem
        work_dir = inp_path.parent

        env = {"OMP_NUM_THREADS": str(num_cpus)}
        cmd = [self._ccx, "-i", job_name]

        logger.info("Running CalculiX: %s in %s", " ".join(cmd), work_dir)

        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(work_dir), env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"CalculiX failed (exit {proc.returncode}): {stderr.decode()}"
            )

        # Collect output files
        dat_file = work_dir / f"{job_name}.dat"
        frd_file = work_dir / f"{job_name}.frd"

        result = {
            "job_name": job_name,
            "return_code": proc.returncode,
            "dat_file": str(dat_file) if dat_file.exists() else None,
            "frd_file": str(frd_file) if frd_file.exists() else None,
        }

        # Auto-parse results if available
        if dat_file.exists():
            dat_content = dat_file.read_text(encoding="utf-8", errors="replace")
            freqs = self._parser.parse_dat_frequencies(dat_content)
            if freqs:
                result["frequencies"] = freqs
            stress = self._parser.parse_dat_stress(dat_content)
            if stress["elements"]:
                result["max_von_mises"] = stress["max_von_mises"]
            disp = self._parser.parse_dat_displacement(dat_content)
            if disp["nodes"]:
                result["max_displacement"] = disp["max_displacement"]

        return result

    async def check_input(self, input_file: str) -> dict[str, Any]:
        """Validate CalculiX input file syntax."""
        inp_path = Path(input_file)
        if not inp_path.exists():
            return {"valid": False, "error": f"File not found: {input_file}"}

        content = inp_path.read_text(encoding="utf-8", errors="replace")
        issues = []

        required_keywords = ["*NODE", "*ELEMENT"]
        for kw in required_keywords:
            if kw not in content.upper():
                issues.append(f"Missing keyword: {kw}")

        if "*STEP" not in content.upper():
            issues.append("Missing *STEP definition")

        if "*END STEP" not in content.upper():
            issues.append("Missing *END STEP")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "line_count": len(content.split("\n")),
        }

    def get_version(self) -> str:
        """Get CalculiX version string."""
        import subprocess
        try:
            result = subprocess.run(
                [self._ccx, "-v"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or result.stderr.strip()
        except FileNotFoundError:
            return "CalculiX not found"
        except Exception as e:
            return f"Error: {e}"
