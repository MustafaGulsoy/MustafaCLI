"""Tests for ApiMapper."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig
from src.plugins.arch_analyzer.analyzers.api_mapper import (
    ApiMapper,
    ApiMap,
    ApiEndpoint,
)


class TestFlaskEndpoints:
    """Tests for Flask route detection."""

    def test_detects_flask_routes(self, python_flask_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_flask_project)
        assert len(api_map.endpoints) > 0

    def test_detects_get_route(self, python_flask_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_flask_project)
        get_endpoints = api_map.get_by_method("GET")
        paths = [ep.path for ep in get_endpoints]
        assert "/api/users" in paths

    def test_detects_post_route(self, python_flask_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_flask_project)
        post_endpoints = api_map.get_by_method("POST")
        paths = [ep.path for ep in post_endpoints]
        assert "/api/users" in paths

    def test_detects_delete_route(self, python_flask_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_flask_project)
        delete_endpoints = api_map.get_by_method("DELETE")
        assert len(delete_endpoints) > 0

    def test_framework_is_flask(self, python_flask_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_flask_project)
        flask_eps = [ep for ep in api_map.endpoints if ep.framework == "Flask"]
        assert len(flask_eps) > 0


class TestFastAPIEndpoints:
    """Tests for FastAPI route detection."""

    def test_detects_fastapi_routes(self, python_fastapi_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_fastapi_project)
        assert len(api_map.endpoints) > 0

    def test_detects_health_endpoint(self, python_fastapi_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_fastapi_project)
        paths = [ep.path for ep in api_map.endpoints]
        assert "/health" in paths

    def test_detects_items_endpoints(self, python_fastapi_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_fastapi_project)
        paths = [ep.path for ep in api_map.endpoints]
        assert "/items" in paths

    def test_framework_is_fastapi(self, python_fastapi_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(python_fastapi_project)
        fastapi_eps = [ep for ep in api_map.endpoints if ep.framework == "FastAPI"]
        assert len(fastapi_eps) > 0


class TestExpressEndpoints:
    """Tests for Express.js route detection."""

    def test_detects_express_routes(self, node_express_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(node_express_project)
        assert len(api_map.endpoints) > 0

    def test_detects_crud_methods(self, node_express_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(node_express_project)
        methods = {ep.method for ep in api_map.endpoints}
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "DELETE" in methods

    def test_detects_users_path(self, node_express_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(node_express_project)
        paths = [ep.path for ep in api_map.endpoints]
        assert "/users" in paths

    def test_framework_is_express(self, node_express_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(node_express_project)
        assert any(ep.framework == "Express" for ep in api_map.endpoints)


class TestAspNetEndpoints:
    """Tests for ASP.NET attribute-based routing."""

    def test_detects_aspnet_routes(self, dotnet_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(dotnet_project)
        assert len(api_map.endpoints) > 0

    def test_detects_http_methods(self, dotnet_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(dotnet_project)
        methods = {ep.method for ep in api_map.endpoints}
        assert "GET" in methods
        assert "POST" in methods
        assert "DELETE" in methods

    def test_handler_includes_controller_name(self, dotnet_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(dotnet_project)
        handlers = [ep.handler for ep in api_map.endpoints]
        assert any("UsersController" in h for h in handlers)

    def test_framework_is_aspnet(self, dotnet_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(dotnet_project)
        assert any(ep.framework == "ASP.NET Core" for ep in api_map.endpoints)


class TestApiMapMethods:
    """Tests for ApiMap filtering methods."""

    def test_get_by_method(self) -> None:
        api_map = ApiMap(endpoints=[
            ApiEndpoint(method="GET", path="/a", handler="h1", source_file="f"),
            ApiEndpoint(method="POST", path="/b", handler="h2", source_file="f"),
            ApiEndpoint(method="GET", path="/c", handler="h3", source_file="f"),
        ])
        gets = api_map.get_by_method("GET")
        assert len(gets) == 2

    def test_get_by_path_prefix(self) -> None:
        api_map = ApiMap(endpoints=[
            ApiEndpoint(method="GET", path="/api/users", handler="h1", source_file="f"),
            ApiEndpoint(method="POST", path="/api/items", handler="h2", source_file="f"),
            ApiEndpoint(method="GET", path="/health", handler="h3", source_file="f"),
        ])
        api_eps = api_map.get_by_path_prefix("/api")
        assert len(api_eps) == 2


class TestEdgeCases:
    """Edge cases for ApiMapper."""

    def test_empty_project(self, empty_project: Path) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints(empty_project)
        assert api_map.endpoints == []

    def test_nonexistent_dir(self) -> None:
        mapper = ApiMapper()
        api_map = mapper.map_endpoints("/nonexistent/path/xyz")
        assert api_map.endpoints == []

    def test_scan_single_file_python(self, python_flask_project: Path) -> None:
        mapper = ApiMapper()
        endpoints = mapper.scan_single_file(python_flask_project / "app.py")
        assert len(endpoints) > 0

    def test_scan_single_file_nonexistent(self) -> None:
        mapper = ApiMapper()
        endpoints = mapper.scan_single_file("/nonexistent/file.py")
        assert endpoints == []
