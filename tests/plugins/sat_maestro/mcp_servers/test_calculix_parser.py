"""Tests for CalculiX result parser."""
import pytest
from unittest.mock import patch, MagicMock

from src.plugins.sat_maestro.mcp_servers.calculix.result_parser import CalculixResultParser


class TestCalculixResultParser:

    def test_parser_init(self):
        parser = CalculixResultParser()
        assert parser is not None

    def test_parse_dat_frequencies(self):
        """Parser extracts modal frequencies from .dat file."""
        dat_content = """
     E I G E N V A L U E   O U T P U T

     MODE NO   EIGENVALUE                      FREQUENCY
                                          (RAD/TIME)      (CYCLES/TIME)

          1   4.8900E+04                 2.2114E+02       3.5200E+01
          2   9.3600E+04                 3.0594E+02       4.8700E+01
          3   1.5240E+05                 3.9038E+02       6.2100E+01
"""
        parser = CalculixResultParser()
        result = parser.parse_dat_frequencies(dat_content)
        assert len(result) == 3
        assert abs(result[0]["frequency_hz"] - 35.2) < 0.1
        assert abs(result[1]["frequency_hz"] - 48.7) < 0.1

    def test_parse_dat_stress(self):
        """Parser extracts stress values from .dat file."""
        dat_content = """
     S T R E S S E S   F O R   S O L I D   E L E M E N T S

     ELEMENT  NODE    SXX         SYY         SZZ         SXY         SXZ         SYZ
         1      1  1.234E+06  2.345E+06  3.456E+06  4.567E+05  5.678E+05  6.789E+05
         1      2  2.234E+06  3.345E+06  4.456E+06  5.567E+05  6.678E+05  7.789E+05
"""
        parser = CalculixResultParser()
        result = parser.parse_dat_stress(dat_content)
        assert result["max_von_mises"] > 0
        assert "elements" in result

    def test_parse_empty_dat(self):
        """Parser handles empty/missing data gracefully."""
        parser = CalculixResultParser()
        result = parser.parse_dat_frequencies("")
        assert result == []
