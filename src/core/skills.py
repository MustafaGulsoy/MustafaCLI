"""
Skills System - Dynamic Task-Specific Knowledge
================================================

Bu modül, Claude Code'un skill sistemini implemente eder.

Skills, task'a özgü best practices ve instructions içeren dosyalardır.
Agent, task'a göre relevant skill'leri dinamik olarak yükler.

Örnek kullanım:
- Python projesi → python.md skill'i yükle
- REST API → fastapi.md veya flask.md yükle
- Frontend → react.md veya vue.md yükle

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json


@dataclass
class Skill:
    """
    Skill definition
    
    Attributes:
        name: Skill'in unique ismi
        description: Ne işe yaradığının açıklaması
        content: Skill içeriği (markdown)
        triggers: Bu skill'i aktive eden keyword'ler
        priority: Öncelik (yüksek = daha önemli)
    """
    name: str
    description: str
    content: str
    triggers: list[str]
    priority: int = 0
    file_path: Optional[str] = None
    
    @classmethod
    def from_file(cls, file_path: str) -> "Skill":
        """
        Markdown dosyasından skill oluştur
        
        Dosya formatı:
        ---
        name: skill_name
        description: What this skill does
        triggers: keyword1, keyword2, keyword3
        priority: 1
        ---
        
        # Skill Content
        ...
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Frontmatter parse
        frontmatter = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        frontmatter[key.strip()] = value.strip()
                content = parts[2].strip()
        
        # Triggers parse
        triggers = []
        if "triggers" in frontmatter:
            triggers = [t.strip() for t in frontmatter["triggers"].split(",")]
        
        return cls(
            name=frontmatter.get("name", Path(file_path).stem),
            description=frontmatter.get("description", ""),
            content=content,
            triggers=triggers,
            priority=int(frontmatter.get("priority", 0)),
            file_path=file_path,
        )


class SkillRegistry:
    """
    Skill registry - skill'leri yönetir ve seçer
    
    Attributes:
        skills_dir: Skill dosyalarının bulunduğu dizin
        skills: Yüklü skill'ler
    """
    
    def __init__(self, skills_dir: Optional[str] = None):
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}
        
        # Built-in skills yükle
        self._load_builtin_skills()
        
        # Custom skills yükle
        if skills_dir and os.path.isdir(skills_dir):
            self._load_skills_from_dir(skills_dir)
    
    def _load_builtin_skills(self):
        """Built-in skill'leri yükle"""
        
        # Python skill
        self._skills["python"] = Skill(
            name="python",
            description="Python development best practices",
            triggers=["python", "py", "pip", "pytest", "django", "flask", "fastapi"],
            priority=1,
            content="""# Python Development Guidelines

## Project Structure
```
project/
├── src/
│   ├── __init__.py
│   └── main.py
├── tests/
│   └── test_main.py
├── pyproject.toml
└── README.md
```

## Best Practices
1. Use type hints for all functions
2. Write docstrings for public functions
3. Use virtual environments (venv or conda)
4. Follow PEP 8 style guide
5. Write tests for all functionality

## Common Commands
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\\Scripts\\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Format code
black .
ruff check --fix .
```

## Error Handling
- Use specific exceptions
- Always clean up resources (use context managers)
- Log errors appropriately
"""
        )
        
        # JavaScript/TypeScript skill
        self._skills["javascript"] = Skill(
            name="javascript",
            description="JavaScript/TypeScript development",
            triggers=["javascript", "js", "typescript", "ts", "node", "npm", "react", "vue", "next"],
            priority=1,
            content="""# JavaScript/TypeScript Guidelines

## Project Structure
```
project/
├── src/
│   ├── index.ts
│   └── utils/
├── tests/
├── package.json
├── tsconfig.json
└── README.md
```

## Best Practices
1. Use TypeScript for type safety
2. Use ESLint and Prettier
3. Write unit tests
4. Use async/await for async operations
5. Handle errors properly

## Common Commands
```bash
# Initialize project
npm init -y

# Install dependencies
npm install

# Run development server
npm run dev

# Build
npm run build

# Test
npm test
```
"""
        )
        
        # Git skill
        self._skills["git"] = Skill(
            name="git",
            description="Git version control",
            triggers=["git", "github", "gitlab", "commit", "branch", "merge"],
            priority=2,
            content="""# Git Guidelines

## Common Workflow
```bash
# Check status
git status

# Stage changes
git add .
git add <file>

# Commit
git commit -m "feat: add new feature"

# Push
git push origin main
```

## Commit Message Format
- feat: New feature
- fix: Bug fix
- docs: Documentation
- style: Formatting
- refactor: Code refactoring
- test: Tests
- chore: Maintenance

## Branching
```bash
# Create branch
git checkout -b feature/new-feature

# Switch branch
git checkout main

# Merge
git merge feature/new-feature
```
"""
        )
        
        # Docker skill
        self._skills["docker"] = Skill(
            name="docker",
            description="Docker containerization",
            triggers=["docker", "dockerfile", "container", "compose", "kubernetes", "k8s"],
            priority=1,
            content="""# Docker Guidelines

## Dockerfile Best Practices
```dockerfile
# Use specific base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first (caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root user
RUN useradd -m appuser
USER appuser

# Expose port
EXPOSE 8000

# Command
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"]
```

## Common Commands
```bash
# Build image
docker build -t myapp .

# Run container
docker run -p 8000:8000 myapp

# Docker Compose
docker-compose up -d
docker-compose down
docker-compose logs -f
```
"""
        )
        
        # API Development skill
        self._skills["api"] = Skill(
            name="api",
            description="REST API development",
            triggers=["api", "rest", "endpoint", "fastapi", "flask", "express"],
            priority=1,
            content="""# API Development Guidelines

## REST Principles
- Use proper HTTP methods (GET, POST, PUT, DELETE)
- Use meaningful resource names
- Return appropriate status codes
- Handle errors consistently
- Version your API

## Status Codes
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 500: Internal Server Error

## FastAPI Example
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    # Implementation
    pass

@app.post("/items", status_code=201)
async def create_item(item: Item):
    # Implementation
    pass
```

## Error Handling
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )
```
"""
        )
        
        # Database skill
        self._skills["database"] = Skill(
            name="database",
            description="Database operations",
            triggers=["database", "db", "sql", "postgres", "mysql", "sqlite", "mongodb", "orm"],
            priority=1,
            content="""# Database Guidelines

## SQL Best Practices
1. Use parameterized queries (prevent SQL injection)
2. Index frequently queried columns
3. Use transactions for multiple operations
4. Normalize data appropriately
5. Use migrations for schema changes

## SQLAlchemy Example
```python
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True)

# Create engine
engine = create_engine("postgresql://user:pass@localhost/db")

# Create session
Session = sessionmaker(bind=engine)
session = Session()

# Query
users = session.query(User).filter(User.name == "John").all()
```

## Migrations (Alembic)
```bash
# Initialize
alembic init migrations

# Create migration
alembic revision --autogenerate -m "Add users table"

# Apply
alembic upgrade head
```
"""
        )
    
    def _load_skills_from_dir(self, skills_dir: str):
        """Dizinden skill'leri yükle"""
        for file_path in Path(skills_dir).glob("**/*.md"):
            try:
                skill = Skill.from_file(str(file_path))
                self._skills[skill.name] = skill
            except Exception as e:
                print(f"Warning: Failed to load skill from {file_path}: {e}")
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """İsme göre skill al"""
        return self._skills.get(name)
    
    def list_skills(self) -> list[str]:
        """Tüm skill isimlerini listele"""
        return list(self._skills.keys())
    
    def find_relevant_skills(
        self,
        query: str,
        context: Optional[str] = None,
        max_skills: int = 3,
    ) -> list[Skill]:
        """
        Query'ye göre relevant skill'leri bul
        
        Args:
            query: Kullanıcı query'si
            context: Ek context (dosya içeriği, hata mesajı, vs.)
            max_skills: Maximum döndürülecek skill sayısı
            
        Returns:
            Relevance'a göre sıralı skill listesi
        """
        query_lower = query.lower()
        context_lower = (context or "").lower()
        combined = f"{query_lower} {context_lower}"
        
        scored_skills = []
        
        for skill in self._skills.values():
            score = 0
            
            # Trigger matching
            for trigger in skill.triggers:
                if trigger.lower() in combined:
                    score += 10
            
            # Name matching
            if skill.name.lower() in combined:
                score += 5
            
            # Priority bonus
            score += skill.priority
            
            if score > 0:
                scored_skills.append((score, skill))
        
        # Sort by score (descending)
        scored_skills.sort(key=lambda x: x[0], reverse=True)
        
        return [skill for _, skill in scored_skills[:max_skills]]
    
    def get_skill_prompt(self, skills: list[Skill]) -> str:
        """
        Skill'leri system prompt'a eklenecek formata çevir
        
        Args:
            skills: Eklenecek skill'ler
            
        Returns:
            Formatted skill content
        """
        if not skills:
            return ""
        
        parts = ["## Relevant Skills\n"]
        
        for skill in skills:
            parts.append(f"### {skill.name}\n")
            parts.append(skill.content)
            parts.append("\n")
        
        return "\n".join(parts)
    
    def register_skill(self, skill: Skill) -> None:
        """Yeni skill kaydet"""
        self._skills[skill.name] = skill


# Default skill'leri yükleyen factory function
def create_skill_registry(skills_dir: Optional[str] = None) -> SkillRegistry:
    """
    Skill registry oluştur
    
    Args:
        skills_dir: Custom skill dizini (optional)
        
    Returns:
        SkillRegistry instance
    """
    return SkillRegistry(skills_dir)
