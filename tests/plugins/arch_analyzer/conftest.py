"""Shared fixtures for arch-analyzer tests.

Builds realistic temporary project directory structures for each major
framework/stack so that every analyzer can be exercised against them.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from src.plugins.arch_analyzer.config import ArchAnalyzerConfig


@pytest.fixture
def config() -> ArchAnalyzerConfig:
    """Default configuration for tests."""
    return ArchAnalyzerConfig()


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """An empty directory -- edge-case baseline."""
    return tmp_path


@pytest.fixture
def python_flask_project(tmp_path: Path) -> Path:
    """A minimal Flask project with routes, models, templates."""
    root = tmp_path / "flask_app"
    root.mkdir()

    # requirements.txt
    (root / "requirements.txt").write_text("flask==3.0.0\nsqlalchemy==2.0.25\n")

    # app.py
    (root / "app.py").write_text(textwrap.dedent("""\
        from flask import Flask, jsonify
        from models.user import User

        app = Flask(__name__)

        @app.route("/")
        def index():
            return jsonify({"status": "ok"})

        @app.get("/api/users")
        def list_users():
            return jsonify([])

        @app.post("/api/users")
        def create_user():
            return jsonify({"id": 1}), 201

        @app.delete("/api/users/<int:user_id>")
        def delete_user(user_id):
            return "", 204
    """))

    # models/
    models = root / "models"
    models.mkdir()
    (models / "__init__.py").write_text("")
    (models / "user.py").write_text(textwrap.dedent("""\
        class User:
            def __init__(self, name: str, email: str):
                self.name = name
                self.email = email
    """))

    # templates/
    templates = root / "templates"
    templates.mkdir()
    (templates / "index.html").write_text("<html><body>Hello</body></html>")

    # routes/
    routes = root / "routes"
    routes.mkdir()
    (routes / "__init__.py").write_text("")
    (routes / "auth.py").write_text(textwrap.dedent("""\
        from flask import Blueprint
        bp = Blueprint("auth", __name__)

        @bp.post("/login")
        def login():
            return {"token": "abc"}
    """))

    return root


@pytest.fixture
def node_express_project(tmp_path: Path) -> Path:
    """A Node.js Express project."""
    root = tmp_path / "express_app"
    root.mkdir()

    pkg = {
        "name": "express-app",
        "version": "1.0.0",
        "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"},
        "devDependencies": {"jest": "^29.0.0", "nodemon": "^3.0.0"},
    }
    (root / "package.json").write_text(json.dumps(pkg, indent=2))

    (root / "index.js").write_text(textwrap.dedent("""\
        const express = require("express");
        const app = express();
        const userRouter = require("./routes/users");
        app.use("/api", userRouter);
        app.listen(3000);
    """))

    routes = root / "routes"
    routes.mkdir()
    (routes / "users.js").write_text(textwrap.dedent("""\
        const express = require("express");
        const router = express.Router();
        const UserController = require("../controllers/userController");

        router.get("/users", UserController.list);
        router.post("/users", UserController.create);
        router.put("/users/:id", UserController.update);
        router.delete("/users/:id", UserController.destroy);

        module.exports = router;
    """))

    controllers = root / "controllers"
    controllers.mkdir()
    (controllers / "userController.js").write_text(textwrap.dedent("""\
        const User = require("../models/User");

        exports.list = (req, res) => res.json([]);
        exports.create = (req, res) => res.json({id: 1});
        exports.update = (req, res) => res.json({ok: true});
        exports.destroy = (req, res) => res.status(204).end();
    """))

    models = root / "models"
    models.mkdir()
    (models / "User.js").write_text(textwrap.dedent("""\
        const mongoose = require("mongoose");
        const schema = new mongoose.Schema({ name: String, email: String });
        module.exports = mongoose.model("User", schema);
    """))

    return root


@pytest.fixture
def python_fastapi_project(tmp_path: Path) -> Path:
    """A FastAPI project with routers, schemas, models."""
    root = tmp_path / "fastapi_app"
    root.mkdir()

    (root / "pyproject.toml").write_text("[project]\nname = 'fastapi-app'\nversion = '0.1.0'\n")

    (root / "main.py").write_text(textwrap.dedent("""\
        from fastapi import FastAPI
        from routers import items, users

        app = FastAPI()
        app.include_router(items.router, prefix="/api")
        app.include_router(users.router, prefix="/api")

        @app.get("/health")
        async def health():
            return {"status": "ok"}
    """))

    routers = root / "routers"
    routers.mkdir()
    (routers / "__init__.py").write_text("")
    (routers / "items.py").write_text(textwrap.dedent("""\
        from fastapi import APIRouter
        from schemas.item import ItemCreate

        router = APIRouter()

        @router.get("/items")
        async def list_items():
            return []

        @router.post("/items")
        async def create_item(item: ItemCreate):
            return {"id": 1}
    """))
    (routers / "users.py").write_text(textwrap.dedent("""\
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/users")
        async def list_users():
            return []

        @router.put("/users/{user_id}")
        async def update_user(user_id: int):
            return {"id": user_id}
    """))

    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "__init__.py").write_text("")
    (schemas / "item.py").write_text(textwrap.dedent("""\
        from pydantic import BaseModel

        class ItemCreate(BaseModel):
            name: str
            price: float
    """))

    models = root / "models"
    models.mkdir()
    (models / "__init__.py").write_text("")
    (models / "database.py").write_text(textwrap.dedent("""\
        from sqlalchemy import create_engine
        engine = create_engine("sqlite:///./test.db")
    """))

    return root


@pytest.fixture
def dotnet_project(tmp_path: Path) -> Path:
    """A .NET ASP.NET Core project."""
    root = tmp_path / "dotnet_app"
    root.mkdir()

    (root / "MyApp.csproj").write_text(textwrap.dedent("""\
        <Project Sdk="Microsoft.NET.Sdk.Web">
          <PropertyGroup>
            <TargetFramework>net8.0</TargetFramework>
          </PropertyGroup>
          <ItemGroup>
            <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
          </ItemGroup>
        </Project>
    """))

    controllers = root / "Controllers"
    controllers.mkdir()
    (controllers / "UsersController.cs").write_text(textwrap.dedent("""\
        using Microsoft.AspNetCore.Mvc;

        [Route("api/[controller]")]
        [ApiController]
        public class UsersController : ControllerBase
        {
            [HttpGet]
            public IActionResult GetAll() => Ok(new List<string>());

            [HttpGet("{id}")]
            public IActionResult GetById(int id) => Ok(id);

            [HttpPost]
            public IActionResult Create() => Created("", null);

            [HttpDelete("{id}")]
            public IActionResult Delete(int id) => NoContent();
        }
    """))

    services = root / "Services"
    services.mkdir()
    (services / "UserService.cs").write_text(textwrap.dedent("""\
        using Microsoft.EntityFrameworkCore;

        public class UserService
        {
            public List<string> GetAll() => new List<string>();
        }
    """))

    models = root / "Models"
    models.mkdir()
    (models / "User.cs").write_text(textwrap.dedent("""\
        public class User
        {
            public int Id { get; set; }
            public string Name { get; set; }
        }
    """))

    return root


@pytest.fixture
def mvc_project(tmp_path: Path) -> Path:
    """A clear MVC-patterned Python project."""
    root = tmp_path / "mvc_app"
    root.mkdir()

    for d in ["models", "views", "controllers"]:
        (root / d).mkdir()
        (root / d / "__init__.py").write_text("")

    (root / "models" / "user.py").write_text(textwrap.dedent("""\
        class User:
            def __init__(self, name: str):
                self.name = name
    """))
    (root / "views" / "user_view.py").write_text(textwrap.dedent("""\
        def render_user(user):
            return f"User: {user.name}"
    """))
    (root / "controllers" / "user_controller.py").write_text(textwrap.dedent("""\
        from models.user import User
        from views.user_view import render_user

        def handle_get_user():
            user = User("Alice")
            return render_user(user)
    """))
    (root / "requirements.txt").write_text("flask==3.0.0\n")

    return root


@pytest.fixture
def circular_deps_project(tmp_path: Path) -> Path:
    """A Python project with intentional circular imports."""
    root = tmp_path / "circular"
    root.mkdir()

    (root / "module_a.py").write_text(textwrap.dedent("""\
        from module_b import func_b

        def func_a():
            return func_b()
    """))
    (root / "module_b.py").write_text(textwrap.dedent("""\
        from module_c import func_c

        def func_b():
            return func_c()
    """))
    (root / "module_c.py").write_text(textwrap.dedent("""\
        from module_a import func_a

        def func_c():
            return func_a()
    """))

    return root


@pytest.fixture
def deeply_nested_project(tmp_path: Path) -> Path:
    """A project with a deeply nested directory structure."""
    root = tmp_path / "nested"
    current = root
    for i in range(12):
        current = current / f"level_{i}"
    current.mkdir(parents=True)
    (current / "deep.py").write_text("x = 1\n")
    return root


@pytest.fixture
def cqrs_project(tmp_path: Path) -> Path:
    """A project with CQRS-style directory layout."""
    root = tmp_path / "cqrs_app"
    root.mkdir()
    for d in ["commands", "queries", "domain", "infrastructure"]:
        (root / d).mkdir()
        (root / d / "__init__.py").write_text("")
    (root / "commands" / "create_order.py").write_text("class CreateOrderCommand: pass\n")
    (root / "queries" / "get_order.py").write_text("class GetOrderQuery: pass\n")
    return root
