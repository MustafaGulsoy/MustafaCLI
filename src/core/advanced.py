"""
Advanced Agent System - Claude CLI'dan Daha İyi
===============================================

Bu modül, Claude CLI'ın eksiklerini gideren gelişmiş özellikler içerir:

1. PARALLEL TOOL EXECUTION - Claude sıralı çalışır, biz paralel
2. PROACTIVE PLANNING - Önce plan yap, sonra execute et
3. SELF-REFLECTION - Kendi çıktısını değerlendir
4. MEMORY SYSTEM - Session arası hafıza
5. CODEBASE AWARENESS - Tüm projeyi anlama
6. SMART ROLLBACK - Hata durumunda geri alma

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable
from collections import defaultdict
import difflib


# =============================================================================
# 1. PLANNING SYSTEM - Claude CLI'da yok
# =============================================================================

class PlanStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """Bir plan adımı"""
    id: str
    description: str
    tool: str
    arguments: dict
    dependencies: list[str] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class ExecutionPlan:
    """
    Execution Plan - Görev için adım adım plan
    
    Claude CLI her seferinde tek tool çağırır ve sonuca göre karar verir.
    Biz önce tam bir plan oluşturur, sonra execute ederiz.
    
    Avantajları:
    - Kullanıcı planı onaylayabilir
    - Paralel execution mümkün
    - Hata durumunda rollback yapılabilir
    - Progress tracking daha kolay
    """
    id: str
    goal: str
    steps: list[PlanStep]
    created_at: datetime = field(default_factory=datetime.now)
    status: PlanStatus = PlanStatus.PENDING
    
    def get_executable_steps(self) -> list[PlanStep]:
        """
        Şu anda execute edilebilir adımları döndür
        (dependency'leri tamamlanmış olanlar)
        """
        completed_ids = {s.id for s in self.steps if s.status == PlanStatus.COMPLETED}
        
        executable = []
        for step in self.steps:
            if step.status != PlanStatus.PENDING:
                continue
            
            # Tüm dependency'ler tamamlanmış mı?
            if all(dep in completed_ids for dep in step.dependencies):
                executable.append(step)
        
        return executable
    
    def get_progress(self) -> tuple[int, int]:
        """(completed, total) döndür"""
        completed = sum(1 for s in self.steps if s.status == PlanStatus.COMPLETED)
        return completed, len(self.steps)
    
    def to_markdown(self) -> str:
        """Plan'ı markdown olarak göster"""
        lines = [f"# Execution Plan: {self.goal}\n"]
        
        for i, step in enumerate(self.steps, 1):
            status_icon = {
                PlanStatus.PENDING: "⏳",
                PlanStatus.IN_PROGRESS: "🔄",
                PlanStatus.COMPLETED: "✅",
                PlanStatus.FAILED: "❌",
                PlanStatus.SKIPPED: "⏭️",
            }.get(step.status, "❓")
            
            lines.append(f"{status_icon} **Step {i}**: {step.description}")
            lines.append(f"   - Tool: `{step.tool}`")
            
            if step.dependencies:
                lines.append(f"   - Depends on: {', '.join(step.dependencies)}")
            
            if step.result:
                lines.append(f"   - Result: {step.result[:100]}...")
            
            if step.error:
                lines.append(f"   - Error: {step.error}")
            
            lines.append("")
        
        return "\n".join(lines)


class Planner:
    """
    Plan oluşturucu
    
    Kullanıcı goal'ünü alır, adım adım plan oluşturur.
    """
    
    def __init__(self, model_provider):
        self.provider = model_provider
    
    async def create_plan(
        self,
        goal: str,
        context: str = "",
        available_tools: list[str] = None,
    ) -> ExecutionPlan:
        """
        Goal için execution plan oluştur
        
        Args:
            goal: Kullanıcının hedefi
            context: Mevcut proje/dosya context'i
            available_tools: Kullanılabilir tool'lar
            
        Returns:
            ExecutionPlan
        """
        tools_str = ", ".join(available_tools or ["bash", "view", "str_replace", "create_file"])
        
        prompt = f"""Analyze this goal and create a detailed execution plan.

GOAL: {goal}

CONTEXT:
{context}

AVAILABLE TOOLS: {tools_str}

Create a step-by-step plan in JSON format:
{{
    "goal": "summarized goal",
    "steps": [
        {{
            "id": "step_1",
            "description": "what this step does",
            "tool": "tool_name",
            "arguments": {{"arg1": "value1"}},
            "dependencies": []  // list of step IDs this depends on
        }}
    ]
}}

Rules:
1. Break down complex tasks into atomic steps
2. Use dependencies to enable parallel execution where possible
3. Include verification steps (view files after editing)
4. Include error handling steps if needed
5. Be specific about file paths and commands

Respond ONLY with the JSON, no other text."""

        response = await self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4096,
        )
        
        # Parse JSON
        content = response.get("content", "")
        
        # Extract JSON from response
        try:
            # Try to find JSON block
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            
            plan_data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            # Fallback: basit plan
            plan_data = {
                "goal": goal,
                "steps": [
                    {
                        "id": "step_1",
                        "description": f"Execute: {goal}",
                        "tool": "bash",
                        "arguments": {"command": "echo 'Manual intervention needed'"},
                        "dependencies": []
                    }
                ]
            }
        
        # Plan oluştur
        steps = []
        for step_data in plan_data.get("steps", []):
            steps.append(PlanStep(
                id=step_data.get("id", f"step_{len(steps)+1}"),
                description=step_data.get("description", ""),
                tool=step_data.get("tool", "bash"),
                arguments=step_data.get("arguments", {}),
                dependencies=step_data.get("dependencies", []),
            ))
        
        return ExecutionPlan(
            id=f"plan_{int(time.time())}",
            goal=plan_data.get("goal", goal),
            steps=steps,
        )


# =============================================================================
# 2. PARALLEL EXECUTION - Claude CLI'da yok
# =============================================================================

class ParallelExecutor:
    """
    Paralel tool execution
    
    Claude CLI tool'ları sıralı çalıştırır. Biz bağımsız tool'ları
    paralel çalıştırarak %50-70 hız kazanabiliriz.
    """
    
    def __init__(self, tool_registry, max_parallel: int = 5):
        self.tools = tool_registry
        self.max_parallel = max_parallel
        self.semaphore = asyncio.Semaphore(max_parallel)
    
    async def execute_step(self, step: PlanStep) -> PlanStep:
        """Tek bir step execute et"""
        async with self.semaphore:
            step.status = PlanStatus.IN_PROGRESS
            start_time = time.time()
            
            try:
                tool = self.tools.get_tool(step.tool)
                if tool is None:
                    raise ValueError(f"Unknown tool: {step.tool}")
                
                result = await tool.execute(**step.arguments)
                
                step.status = PlanStatus.COMPLETED if result.success else PlanStatus.FAILED
                step.result = result.output
                step.error = result.error
                
            except Exception as e:
                step.status = PlanStatus.FAILED
                step.error = str(e)
            
            step.duration_ms = int((time.time() - start_time) * 1000)
            return step
    
    async def execute_plan(
        self,
        plan: ExecutionPlan,
        on_step_complete: Optional[Callable[[PlanStep], None]] = None,
    ) -> ExecutionPlan:
        """
        Plan'ı execute et - mümkün olduğunca paralel
        
        Args:
            plan: Execute edilecek plan
            on_step_complete: Her step tamamlandığında çağrılacak callback
            
        Returns:
            Güncellenmiş plan
        """
        plan.status = PlanStatus.IN_PROGRESS
        
        while True:
            # Execute edilebilir step'leri al
            executable = plan.get_executable_steps()
            
            if not executable:
                # Hiç executable step kalmadı
                # Pending step var mı kontrol et
                pending = [s for s in plan.steps if s.status == PlanStatus.PENDING]
                if pending:
                    # Deadlock veya dependency hatası
                    for step in pending:
                        step.status = PlanStatus.SKIPPED
                        step.error = "Dependency not met"
                break
            
            # Paralel execute
            tasks = [self.execute_step(step) for step in executable]
            completed_steps = await asyncio.gather(*tasks)
            
            # Callbacks
            if on_step_complete:
                for step in completed_steps:
                    on_step_complete(step)
            
            # Hata kontrolü - bir step fail ederse devam et mi?
            failed = [s for s in completed_steps if s.status == PlanStatus.FAILED]
            if failed:
                # Dependent step'leri skip et
                failed_ids = {s.id for s in failed}
                for step in plan.steps:
                    if step.status == PlanStatus.PENDING:
                        if any(dep in failed_ids for dep in step.dependencies):
                            step.status = PlanStatus.SKIPPED
                            step.error = f"Dependency failed: {step.dependencies}"
        
        # Final status
        if all(s.status == PlanStatus.COMPLETED for s in plan.steps):
            plan.status = PlanStatus.COMPLETED
        elif any(s.status == PlanStatus.FAILED for s in plan.steps):
            plan.status = PlanStatus.FAILED
        else:
            plan.status = PlanStatus.COMPLETED  # Partial success
        
        return plan


# =============================================================================
# 3. SELF-REFLECTION - Claude CLI'da yok
# =============================================================================

@dataclass
class ReflectionResult:
    """Self-reflection sonucu"""
    is_correct: bool
    confidence: float  # 0-1
    issues: list[str]
    suggestions: list[str]
    should_retry: bool


class SelfReflector:
    """
    Self-reflection sistemi
    
    Agent kendi çıktısını değerlendirir ve gerekirse düzeltir.
    Bu, Claude CLI'ın en büyük eksiklerinden biri.
    """
    
    def __init__(self, model_provider):
        self.provider = model_provider
    
    async def reflect(
        self,
        goal: str,
        actions_taken: list[dict],
        final_output: str,
        context: str = "",
    ) -> ReflectionResult:
        """
        Yapılan işlemleri değerlendir
        
        Args:
            goal: Orijinal hedef
            actions_taken: Yapılan tool calls ve sonuçları
            final_output: Son çıktı
            context: Ek context
            
        Returns:
            ReflectionResult
        """
        actions_str = "\n".join([
            f"- {a['tool']}({a['args']}): {a['result'][:200]}..."
            for a in actions_taken[-10:]  # Son 10 action
        ])
        
        prompt = f"""You are a code reviewer. Evaluate if the goal was achieved correctly.

GOAL: {goal}

ACTIONS TAKEN:
{actions_str}

FINAL OUTPUT:
{final_output[:2000]}

CONTEXT:
{context[:1000]}

Evaluate and respond in JSON format:
{{
    "is_correct": true/false,
    "confidence": 0.0-1.0,
    "issues": ["list of issues found"],
    "suggestions": ["list of improvement suggestions"],
    "should_retry": true/false
}}

Be critical but fair. Check for:
1. Does the output match the goal?
2. Are there any bugs or errors?
3. Is the code quality acceptable?
4. Are there edge cases not handled?
5. Is the solution complete?

Respond ONLY with JSON."""

        response = await self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1024,
        )
        
        try:
            content = response.get("content", "")
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            else:
                json_str = content
            
            data = json.loads(json_str.strip())
            
            return ReflectionResult(
                is_correct=data.get("is_correct", True),
                confidence=data.get("confidence", 0.5),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                should_retry=data.get("should_retry", False),
            )
        except:
            return ReflectionResult(
                is_correct=True,
                confidence=0.5,
                issues=[],
                suggestions=[],
                should_retry=False,
            )
    
    async def generate_fix(
        self,
        goal: str,
        reflection: ReflectionResult,
        current_code: str,
    ) -> str:
        """
        Reflection'a göre fix öner
        
        Returns:
            Düzeltilmiş kod veya boş string
        """
        if reflection.is_correct or not reflection.should_retry:
            return ""
        
        prompt = f"""Fix the following code based on the issues found.

GOAL: {goal}

ISSUES:
{chr(10).join(f'- {issue}' for issue in reflection.issues)}

SUGGESTIONS:
{chr(10).join(f'- {s}' for s in reflection.suggestions)}

CURRENT CODE:
```
{current_code}
```

Provide the fixed code. If no fix is needed, respond with "NO_FIX_NEEDED"."""

        response = await self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4096,
        )
        
        content = response.get("content", "")
        if "NO_FIX_NEEDED" in content:
            return ""
        
        # Extract code from response
        if "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                code = parts[1]
                if code.startswith(("python", "javascript", "typescript", "java", "go")):
                    code = code.split("\n", 1)[1] if "\n" in code else code
                return code.strip()
        
        return content


# =============================================================================
# 4. CODEBASE AWARENESS - Claude CLI'da sınırlı
# =============================================================================

@dataclass
class FileInfo:
    """Dosya bilgisi"""
    path: str
    language: str
    size: int
    lines: int
    imports: list[str]
    exports: list[str]
    functions: list[str]
    classes: list[str]
    last_modified: float
    content_hash: str


@dataclass
class CodebaseIndex:
    """
    Codebase index - tüm projeyi anlama
    
    Claude CLI her seferinde dosyaları okur. Biz bir index tutarak
    çok daha hızlı ve akıllı navigasyon sağlarız.
    """
    root_dir: str
    files: dict[str, FileInfo] = field(default_factory=dict)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    symbol_index: dict[str, list[str]] = field(default_factory=dict)  # symbol -> [file paths]
    created_at: datetime = field(default_factory=datetime.now)
    
    def get_related_files(self, file_path: str, max_depth: int = 2) -> list[str]:
        """
        Bir dosyayla ilişkili dosyaları bul
        
        Import/export ilişkilerine göre related files döndür.
        """
        related = set()
        to_visit = [(file_path, 0)]
        visited = set()
        
        while to_visit:
            current, depth = to_visit.pop(0)
            if current in visited or depth > max_depth:
                continue
            
            visited.add(current)
            
            # Direct dependencies
            deps = self.dependency_graph.get(current, [])
            for dep in deps:
                related.add(dep)
                if depth < max_depth:
                    to_visit.append((dep, depth + 1))
            
            # Reverse dependencies (who imports this file)
            for other_file, other_deps in self.dependency_graph.items():
                if current in other_deps:
                    related.add(other_file)
                    if depth < max_depth:
                        to_visit.append((other_file, depth + 1))
        
        related.discard(file_path)
        return list(related)
    
    def find_symbol(self, symbol: str) -> list[str]:
        """Symbol'ü içeren dosyaları bul"""
        return self.symbol_index.get(symbol, [])
    
    def get_project_summary(self) -> str:
        """Proje özeti"""
        languages = defaultdict(int)
        total_lines = 0
        
        for file_info in self.files.values():
            languages[file_info.language] += 1
            total_lines += file_info.lines
        
        summary = [
            f"Project: {os.path.basename(self.root_dir)}",
            f"Total files: {len(self.files)}",
            f"Total lines: {total_lines:,}",
            f"Languages: {dict(languages)}",
            f"Last indexed: {self.created_at.isoformat()}",
        ]
        
        return "\n".join(summary)


class CodebaseIndexer:
    """
    Codebase indexer - projeyi analiz et ve index oluştur
    """
    
    LANGUAGE_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".cs": "csharp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
    }
    
    IGNORE_DIRS = {
        "node_modules", "__pycache__", ".git", ".svn", ".hg",
        "venv", ".venv", "env", "dist", "build", ".cache",
        ".pytest_cache", ".mypy_cache", "target", "bin", "obj",
    }
    
    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
    
    async def index(self) -> CodebaseIndex:
        """Codebase'i indexle"""
        index = CodebaseIndex(root_dir=self.root_dir)
        
        for root, dirs, files in os.walk(self.root_dir):
            # Ignore directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in self.LANGUAGE_EXTENSIONS:
                    continue
                
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.root_dir)
                
                try:
                    file_info = await self._analyze_file(file_path, ext)
                    index.files[rel_path] = file_info
                    
                    # Symbol index güncelle
                    for symbol in file_info.functions + file_info.classes + file_info.exports:
                        if symbol not in index.symbol_index:
                            index.symbol_index[symbol] = []
                        index.symbol_index[symbol].append(rel_path)
                    
                    # Dependency graph güncelle
                    index.dependency_graph[rel_path] = file_info.imports
                    
                except Exception as e:
                    # Skip problematic files
                    continue
        
        return index
    
    async def _analyze_file(self, file_path: str, ext: str) -> FileInfo:
        """Tek bir dosyayı analiz et"""
        language = self.LANGUAGE_EXTENSIONS.get(ext, "unknown")
        
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        lines = content.split("\n")
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Language-specific analysis
        imports = []
        exports = []
        functions = []
        classes = []
        
        if language == "python":
            imports, exports, functions, classes = self._analyze_python(content)
        elif language in ("javascript", "typescript"):
            imports, exports, functions, classes = self._analyze_js_ts(content)
        
        return FileInfo(
            path=file_path,
            language=language,
            size=len(content),
            lines=len(lines),
            imports=imports,
            exports=exports,
            functions=functions,
            classes=classes,
            last_modified=os.path.getmtime(file_path),
            content_hash=content_hash,
        )
    
    def _analyze_python(self, content: str) -> tuple:
        """Python dosyasını analiz et"""
        import re
        
        imports = []
        exports = []
        functions = []
        classes = []
        
        # Imports
        for match in re.finditer(r'^(?:from\s+(\S+)\s+)?import\s+(.+)$', content, re.MULTILINE):
            module = match.group(1) or match.group(2).split(',')[0].split()[0]
            imports.append(module.strip())
        
        # Functions
        for match in re.finditer(r'^def\s+(\w+)\s*\(', content, re.MULTILINE):
            functions.append(match.group(1))
        
        # Classes
        for match in re.finditer(r'^class\s+(\w+)\s*[:\(]', content, re.MULTILINE):
            classes.append(match.group(1))
        
        # Exports (__all__)
        all_match = re.search(r'__all__\s*=\s*\[([^\]]+)\]', content)
        if all_match:
            exports = [s.strip().strip("'\"") for s in all_match.group(1).split(',')]
        else:
            # Public symbols (don't start with _)
            exports = [f for f in functions if not f.startswith('_')]
            exports += [c for c in classes if not c.startswith('_')]
        
        return imports, exports, functions, classes
    
    def _analyze_js_ts(self, content: str) -> tuple:
        """JavaScript/TypeScript dosyasını analiz et"""
        import re
        
        imports = []
        exports = []
        functions = []
        classes = []
        
        # Imports
        for match in re.finditer(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", content):
            imports.append(match.group(1))
        
        # Functions
        for match in re.finditer(r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)', content):
            name = match.group(1) or match.group(2)
            if name:
                functions.append(name)
        
        # Classes
        for match in re.finditer(r'class\s+(\w+)', content):
            classes.append(match.group(1))
        
        # Exports
        for match in re.finditer(r'export\s+(?:default\s+)?(?:const|let|var|function|class)\s+(\w+)', content):
            exports.append(match.group(1))
        
        return imports, exports, functions, classes


# =============================================================================
# 5. PERSISTENT MEMORY - Claude CLI'da yok
# =============================================================================

class PersistentMemory:
    """
    Session arası kalıcı hafıza
    
    Claude CLI her session'da sıfırdan başlar.
    Biz önceki session'lardan öğrenilen bilgileri saklarız.
    """
    
    def __init__(self, db_path: str = "~/.local-agent/memory.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Database oluştur"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Facts table - öğrenilen bilgiler
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category, key)
            )
        """)
        
        # Projects table - proje bilgileri
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                name TEXT,
                language TEXT,
                framework TEXT,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # Patterns table - öğrenilen pattern'ler
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                replacement TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Commands history - başarılı komutlar
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                context TEXT,
                success INTEGER,
                output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def remember_fact(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        source: str = None,
    ):
        """Bir bilgiyi hafızaya kaydet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO facts (category, key, value, confidence, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(category, key) DO UPDATE SET
                value = excluded.value,
                confidence = excluded.confidence,
                updated_at = CURRENT_TIMESTAMP
        """, (category, key, value, confidence, source))
        
        conn.commit()
        conn.close()
    
    def recall_fact(self, category: str, key: str) -> Optional[str]:
        """Bir bilgiyi hatırla"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT value FROM facts WHERE category = ? AND key = ?",
            (category, key)
        )
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def recall_category(self, category: str) -> dict[str, str]:
        """Bir kategorideki tüm bilgileri hatırla"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT key, value FROM facts WHERE category = ?",
            (category,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return {row[0]: row[1] for row in rows}
    
    def remember_project(self, path: str, **metadata):
        """Proje bilgisini kaydet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO projects (path, name, language, framework, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name = excluded.name,
                language = excluded.language,
                framework = excluded.framework,
                metadata = excluded.metadata,
                last_accessed = CURRENT_TIMESTAMP
        """, (
            path,
            metadata.get("name"),
            metadata.get("language"),
            metadata.get("framework"),
            json.dumps(metadata),
        ))
        
        conn.commit()
        conn.close()
    
    def recall_project(self, path: str) -> Optional[dict]:
        """Proje bilgisini hatırla"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM projects WHERE path = ?", (path,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "path": row[1],
            "name": row[2],
            "language": row[3],
            "framework": row[4],
            "last_accessed": row[5],
            "metadata": json.loads(row[6]) if row[6] else {},
        }
    
    def learn_pattern(self, pattern_type: str, pattern: str, replacement: str = None):
        """Yeni pattern öğren"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO patterns (pattern_type, pattern, replacement)
            VALUES (?, ?, ?)
        """, (pattern_type, pattern, replacement))
        
        conn.commit()
        conn.close()
    
    def record_command(self, command: str, context: str, success: bool, output: str):
        """Komut geçmişine kaydet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO command_history (command, context, success, output)
            VALUES (?, ?, ?, ?)
        """, (command, context, 1 if success else 0, output[:10000]))
        
        conn.commit()
        conn.close()
    
    def get_similar_commands(self, context: str, limit: int = 5) -> list[dict]:
        """Benzer context'te başarılı komutları getir"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Simple keyword matching - production'da embedding kullan
        keywords = context.lower().split()[:5]
        
        results = []
        for keyword in keywords:
            cursor.execute("""
                SELECT command, context, output FROM command_history
                WHERE success = 1 AND context LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (f"%{keyword}%", limit))
            results.extend(cursor.fetchall())
        
        conn.close()
        
        # Deduplicate
        seen = set()
        unique = []
        for row in results:
            if row[0] not in seen:
                seen.add(row[0])
                unique.append({
                    "command": row[0],
                    "context": row[1],
                    "output": row[2],
                })
        
        return unique[:limit]


# =============================================================================
# 6. SMART ROLLBACK - Claude CLI'da yok
# =============================================================================

@dataclass
class FileSnapshot:
    """Dosya snapshot'ı"""
    path: str
    content: str
    timestamp: float
    
    def diff(self, other: "FileSnapshot") -> str:
        """İki snapshot arasındaki fark"""
        diff = difflib.unified_diff(
            other.content.splitlines(keepends=True),
            self.content.splitlines(keepends=True),
            fromfile=f"a/{self.path}",
            tofile=f"b/{self.path}",
        )
        return "".join(diff)


class RollbackManager:
    """
    Rollback manager - değişiklikleri geri alma
    
    Claude CLI hata yaptığında manual fix gerektirir.
    Biz otomatik rollback yapabiliriz.
    """
    
    def __init__(self, working_dir: str):
        self.working_dir = working_dir
        self.snapshots: dict[str, list[FileSnapshot]] = defaultdict(list)
        self.max_snapshots = 10
    
    def take_snapshot(self, file_path: str) -> Optional[FileSnapshot]:
        """Dosyanın snapshot'ını al"""
        full_path = os.path.join(self.working_dir, file_path)
        
        if not os.path.exists(full_path):
            return None
        
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            snapshot = FileSnapshot(
                path=file_path,
                content=content,
                timestamp=time.time(),
            )
            
            # Snapshot'ı kaydet
            self.snapshots[file_path].append(snapshot)
            
            # Max snapshot sayısını aşma
            if len(self.snapshots[file_path]) > self.max_snapshots:
                self.snapshots[file_path].pop(0)
            
            return snapshot
            
        except Exception:
            return None
    
    def rollback(self, file_path: str, steps: int = 1) -> bool:
        """
        Dosyayı belirli adım geri al
        
        Args:
            file_path: Dosya yolu
            steps: Kaç adım geri gidilecek
            
        Returns:
            Başarılı mı
        """
        if file_path not in self.snapshots:
            return False
        
        history = self.snapshots[file_path]
        if len(history) < steps + 1:
            return False
        
        # steps kadar geriye git
        target_snapshot = history[-(steps + 1)]
        
        full_path = os.path.join(self.working_dir, file_path)
        
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(target_snapshot.content)
            
            # İleri snapshot'ları sil
            self.snapshots[file_path] = history[:-(steps)]
            
            return True
            
        except Exception:
            return False
    
    def get_history(self, file_path: str) -> list[dict]:
        """Dosya geçmişini getir"""
        if file_path not in self.snapshots:
            return []
        
        history = []
        snapshots = self.snapshots[file_path]
        
        for i, snapshot in enumerate(snapshots):
            entry = {
                "index": i,
                "timestamp": snapshot.timestamp,
                "size": len(snapshot.content),
                "lines": snapshot.content.count("\n") + 1,
            }
            
            # Diff from previous
            if i > 0:
                entry["diff_lines"] = len(snapshot.diff(snapshots[i-1]).splitlines())
            
            history.append(entry)
        
        return history
    
    def rollback_all(self) -> dict[str, bool]:
        """Tüm dosyaları başlangıç noktasına geri al"""
        results = {}
        
        for file_path in list(self.snapshots.keys()):
            if self.snapshots[file_path]:
                # İlk snapshot'a geri dön
                steps = len(self.snapshots[file_path]) - 1
                if steps > 0:
                    results[file_path] = self.rollback(file_path, steps)
        
        return results
