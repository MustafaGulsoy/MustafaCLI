"""Tests for Gmsh mesher wrapper."""
import pytest
from unittest.mock import patch, MagicMock

from src.plugins.sat_maestro.mcp_servers.gmsh.mesher import GmshMesher


class TestGmshMesher:

    def test_mesher_init(self):
        mesher = GmshMesher()
        assert mesher is not None

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_mesh_from_step(self, mock_gmsh):
        """Mesher calls gmsh API to generate mesh from STEP."""
        mock_gmsh.model.mesh.getNodes.return_value = ([1, 2, 3], [0]*9, [])
        mock_gmsh.model.mesh.getElements.return_value = ([4], [[1, 2]], [[1, 2, 3, 4]])
        mesher = GmshMesher()
        result = mesher.mesh_from_step("test.step", element_size=5.0)
        mock_gmsh.initialize.assert_called_once()
        mock_gmsh.open.assert_called_once_with("test.step")
        assert "mesh_file" in result

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_mesh_quality_check(self, mock_gmsh):
        """Mesher returns quality metrics."""
        mock_gmsh.model.mesh.getElementQualities.return_value = [0.8, 0.9, 0.7]
        mesher = GmshMesher()
        result = mesher.quality_check("test.msh")
        assert "min_quality" in result
        assert "avg_quality" in result

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_mesh_info(self, mock_gmsh):
        """Mesher returns mesh statistics."""
        mock_gmsh.model.mesh.getNodes.return_value = ([1,2,3], [0]*9, [])
        mock_gmsh.model.mesh.getElements.return_value = ([4], [[1,2]], [[1,2,3,4,5,6,7,8]])
        mesher = GmshMesher()
        result = mesher.info("test.msh")
        assert "node_count" in result

    @patch("src.plugins.sat_maestro.mcp_servers.gmsh.mesher.gmsh")
    def test_convert_format(self, mock_gmsh):
        """Mesher converts mesh to different format."""
        mesher = GmshMesher()
        result = mesher.convert("test.msh", "inp")
        mock_gmsh.write.assert_called()
        assert result.endswith(".inp")
