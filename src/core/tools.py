"""
Tool System - Claude Code Tool Architecture
============================================

Bu modül, Claude Code'un tool sisteminin implementasyonunu içerir.

Temel Prensipler:
1. Minimal ama güçlü tool seti
2. Her tool tek bir şeyi iyi yapmalı
3. Output truncation ve smart formatting
4. Robust error handling
5. Security-first design

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import json
import shlex
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from pathlib import Path

from .constants import (
    MAX_FILE_SIZE_CHARS,
    MAX_OUTPUT_CHARS,
    MAX_DIR_ENTRIES,
    MAX_DIR_DEPTH,
    BLOCKED_COMMAND_PATTERNS,
    IGNORE_PATTERNS,
    DEFAULT_BASH_TIMEOUT,
    DEFAULT_TOOL_TIMEOUT,
)
from .exceptions import (
    ToolExecutionError,
    ToolTimeoutError,
    CommandBlockedError,
    PathTraversalError,
    SecurityError,
)
from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ToolResult:
    """
    Tool execution sonucu
    
    Attributes:
        success: İşlem başarılı mı
        output: Tool'un output'u (truncated olabilir)
        error: Hata mesajı (varsa)
        metadata: Ek bilgiler (file paths, line counts, etc.)
    """
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[dict] = None
    
    def to_model_format(self) -> str:
        """Model'e gönderilecek format"""
        if self.success:
            return self.output
        else:
            return f"Error: {self.error}\n\nPartial output:\n{self.output}" if self.output else f"Error: {self.error}"


class Tool(ABC):
    """
    Abstract base tool class
    
    Her tool bu class'ı extend etmeli ve gerekli methodları implemente etmeli.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool'un unique ismi"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool'un ne yaptığının açıklaması - model bunu görür"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema formatında parametre tanımları"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Tool'u çalıştır"""
        pass
    
    def get_definition(self) -> dict:
        """Model'e gönderilecek tool definition"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class ToolRegistry:
    """
    Tool registry - tool'ları yönetir
    
    Bu class, tüm tool'ları kaydeder ve model'e tool definitions sağlar.
    """
    
    def __init__(self):
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Tool kaydet"""
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Tool al"""
        return self._tools.get(name)
    
    def get_tool_definitions(self) -> list[dict]:
        """Tüm tool definitions"""
        return [tool.get_definition() for tool in self._tools.values()]
    
    def list_tools(self) -> list[str]:
        """Kayıtlı tool isimleri"""
        return list(self._tools.keys())


# =============================================================================
# Core Tools - Claude Code'un temel tool seti
# =============================================================================

class BashTool(Tool):
    """
    Bash command execution tool
    
    Bu tool, Claude Code'un en güçlü tool'u. Neredeyse her şeyi yapabilir.
    Güvenlik için command filtering ve timeout uygulanır.
    
    Attributes:
        working_dir: Komutların çalışacağı dizin
        timeout: Maximum execution time (saniye)
        blocked_patterns: Engellenen command pattern'leri
    """
    
    name = "bash"
    description = """Execute a bash command in the working directory.

Use this tool for:
- Running shell commands (ls, cat, grep, find, etc.)
- Installing packages (pip, npm, apt)
- Running scripts and tests
- Git operations
- File operations that don't need precision editing

The command runs in a bash shell with the working directory set appropriately.
Output is captured and returned. Long outputs are truncated from the middle."""
    
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Optional timeout in seconds (default: 120)",
                "default": 120
            }
        },
        "required": ["command"]
    }
    
    # Whitelist of safe command prefixes
    SAFE_COMMANDS = {
        # Unix
        "ls", "cat", "head", "tail", "grep", "find", "echo", "pwd", "cd",
        "mkdir", "touch", "cp", "mv", "chmod", "chown", "wc", "sort", "tree",
        # Windows
        "dir", "type", "where", "findstr", "copy", "move", "del", "ren",
        "set", "ver", "whoami", "hostname", "ipconfig", "systeminfo",
        "powershell", "cmd",
        # Shell builtins
        "if", "for", "while", "test", "[", "[[", "true", "false",
        # Dev tools
        "git", "python", "python3", "pip", "pip3", "npm", "node", "npx",
        "cargo", "rustc", "go", "javac", "java",
        "make", "cmake", "gcc", "g++", "clang",
        "docker", "kubectl", "helm",
        "pytest", "npm test", "cargo test",
        "dotnet", "ollama",
    }

    def __init__(
        self,
        working_dir: str = ".",
        timeout: int = DEFAULT_BASH_TIMEOUT,
        blocked_patterns: Optional[list[str]] = None,
        max_output_chars: int = MAX_OUTPUT_CHARS,
        allow_dangerous: bool = False,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.allow_dangerous = allow_dangerous
        self.blocked_patterns = blocked_patterns or BLOCKED_COMMAND_PATTERNS
    
    def _validate_command(self, command: str) -> None:
        """
        Validate command for security.

        Raises:
            CommandBlockedError: If command is blocked
        """
        # Check blocked patterns
        for pattern in self.blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning(
                    "command_blocked",
                    command=command[:100],
                    pattern=pattern,
                    working_dir=str(self.working_dir),
                )
                raise CommandBlockedError(
                    message="Command blocked by security policy",
                    command=command,
                    pattern=pattern,
                )

        # Check command whitelist (if not allowing dangerous commands)
        if not self.allow_dangerous:
            # Extract command name (first word)
            cmd_parts = shlex.split(command)
            if cmd_parts:
                cmd_name = cmd_parts[0].lower()
                # Check if command or its base is in whitelist
                if not any(
                    cmd_name.startswith(safe_cmd.lower())
                    for safe_cmd in self.SAFE_COMMANDS
                ):
                    logger.warning(
                        "unsafe_command",
                        command=command[:100],
                        cmd_name=cmd_name,
                        working_dir=str(self.working_dir),
                    )
                    raise SecurityError(
                        f"Command '{cmd_name}' not in whitelist. Set allow_dangerous=True to override."
                    )

    async def execute(self, command: str, timeout: Optional[int] = None) -> ToolResult:
        """
        Bash komutunu çalıştır

        Args:
            command: Çalıştırılacak komut
            timeout: Override timeout

        Returns:
            ToolResult: Komut sonucu
        """
        # Coerce timeout to int (models sometimes send strings)
        if timeout is not None:
            try:
                timeout = int(timeout)
            except (ValueError, TypeError):
                timeout = None

        logger.debug(
            "tool_execute_start",
            tool="bash",
            command=command[:100],
            working_dir=str(self.working_dir),
        )

        # Güvenlik kontrolü
        try:
            self._validate_command(command)
        except (CommandBlockedError, SecurityError) as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        effective_timeout = timeout or self.timeout

        # On Windows, run through Git Bash so real Unix commands work (ls -la, grep, etc.)
        if sys.platform == "win32":
            escaped = command.replace("'", "'\\''")
            shell_command = f"bash -c '{escaped}'"
        else:
            shell_command = command

        try:
            # Async subprocess
            process = await asyncio.create_subprocess_shell(
                shell_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env={**os.environ, "TERM": "dumb"},  # Disable colors for cleaner output
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {effective_timeout} seconds"
                )
            
            # Output'u decode et
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")
            
            # Output'u birleştir
            output = stdout_str
            if stderr_str:
                if output:
                    output += "\n\n--- STDERR ---\n"
                output += stderr_str
            
            # Truncation
            output = self._smart_truncate(output)
            
            return ToolResult(
                success=process.returncode == 0,
                output=output,
                error=None if process.returncode == 0 else f"Exit code: {process.returncode}",
                metadata={"exit_code": process.returncode}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to execute command: {str(e)}"
            )
    
    def _smart_truncate(self, text: str) -> str:
        """
        Akıllı truncation - ortadan kes, baş ve son koru
        
        Bu, Claude Code'un yaptığı gibi. Log dosyaları gibi uzun output'larda
        baş ve son genellikle en önemli kısımlar.
        """
        if len(text) <= self.max_output_chars:
            return text
        
        # Baş ve sondan eşit parça al
        half = self.max_output_chars // 2
        truncated_chars = len(text) - self.max_output_chars
        
        return (
            text[:half] +
            f"\n\n... [{truncated_chars:,} characters truncated] ...\n\n" +
            text[-half:]
        )


class ViewTool(Tool):
    """
    File/directory viewing tool
    
    Bu tool, dosya ve dizin içeriklerini görüntüler.
    Line numbers ile dosya okuma, akıllı truncation, ve dizin listesi.
    """
    
    name = "view"
    description = """View file contents or directory listing.

For files:
- Shows content with line numbers
- Supports optional line range: [start, end] or [start, -1] for start to end
- Long files are truncated from the middle, preserving beginning and end

For directories:
- Shows tree structure up to 2 levels deep
- Ignores hidden files and common noise (node_modules, __pycache__, etc.)

Use this tool before editing files to understand their structure."""
    
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to file or directory"
            },
            "line_range": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Optional [start, end] line range. Use -1 for end to mean 'until end of file'"
            }
        },
        "required": ["path"]
    }
    
    # Ignore patterns for directory listing
    IGNORE_PATTERNS = {
        "node_modules", "__pycache__", ".git", ".svn", ".hg",
        ".idea", ".vscode", ".vs", "venv", ".venv", "env",
        ".env", "dist", "build", ".cache", ".pytest_cache",
        ".mypy_cache", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db"
    }
    
    def __init__(
        self,
        working_dir: str = ".",
        max_file_chars: int = MAX_FILE_SIZE_CHARS,
        max_dir_entries: int = MAX_DIR_ENTRIES,
        max_depth: int = MAX_DIR_DEPTH,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.max_file_chars = max_file_chars
        self.max_dir_entries = max_dir_entries
        self.max_depth = max_depth

    def _validate_path(self, path: Path) -> None:
        """
        Validate path for security (prevent path traversal).

        Raises:
            PathTraversalError: If path escapes working directory
        """
        try:
            resolved_path = path.resolve(strict=False)
            # Check if path is within working directory
            resolved_path.relative_to(self.working_dir)
        except ValueError:
            logger.warning(
                "path_traversal_attempt",
                path=str(path),
                working_dir=str(self.working_dir),
            )
            raise PathTraversalError(
                message="Path traversal attempt detected",
                path=str(path),
            )
    
    async def execute(
        self,
        path: str,
        line_range: Optional[list[int]] = None
    ) -> ToolResult:
        """
        Dosya veya dizini görüntüle

        Args:
            path: Dosya veya dizin yolu
            line_range: [start, end] line aralığı (optional)

        Returns:
            ToolResult: İçerik veya hata
        """
        logger.debug("tool_execute_start", tool="view", path=path)

        # Path'i resolve et
        if Path(path).is_absolute():
            full_path = Path(path)
        else:
            full_path = self.working_dir / path

        full_path = full_path.resolve()

        # Security check
        try:
            self._validate_path(full_path)
        except PathTraversalError as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )

        # Var mı kontrol et
        if not full_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Path not found: {path}"
            )

        # Dizin mi dosya mı?
        if full_path.is_dir():
            return await self._view_directory(full_path)
        else:
            return await self._view_file(full_path, line_range)
    
    async def _view_file(
        self,
        path: Path,
        line_range: Optional[list[int]] = None
    ) -> ToolResult:
        """Dosya içeriğini görüntüle"""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            # Line range uygula
            if line_range:
                start, end = line_range
                if end == -1:
                    end = total_lines
                
                # Bounds check
                start = max(1, min(start, total_lines))
                end = max(start, min(end, total_lines))
                
                selected_lines = lines[start - 1:end]
                start_num = start
            else:
                selected_lines = lines
                start_num = 1
            
            # Line numbers ekle
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start_num):
                # Tab'ları space'e çevir (daha tutarlı görünüm)
                line_content = line.rstrip("\n\r").replace("\t", "    ")
                numbered_lines.append(f"{i:6d}: {line_content}")
            
            output = "\n".join(numbered_lines)
            
            # Truncation
            if len(output) > self.max_file_chars:
                output = self._smart_truncate(output)
            
            # Metadata
            metadata = {
                "total_lines": total_lines,
                "shown_lines": len(selected_lines),
                "file_size": path.stat().st_size,
            }
            
            if line_range:
                metadata["line_range"] = [start_num, start_num + len(selected_lines) - 1]
            
            return ToolResult(
                success=True,
                output=output,
                metadata=metadata
            )
            
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                output="",
                error="File appears to be binary. Cannot display as text."
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to read file: {str(e)}"
            )
    
    async def _view_directory(self, path: Path) -> ToolResult:
        """Dizin yapısını görüntüle"""
        try:
            lines = []
            entry_count = 0
            
            def should_ignore(name: str) -> bool:
                """Ignore edilmeli mi?"""
                if name.startswith("."):
                    return True
                return name in self.IGNORE_PATTERNS
            
            def walk_dir(dir_path: str, prefix: str = "", depth: int = 0):
                """Recursive directory walk"""
                nonlocal entry_count
                
                if depth > self.max_depth or entry_count >= self.max_dir_entries:
                    return
                
                try:
                    entries = sorted(os.listdir(dir_path))
                except PermissionError:
                    lines.append(f"{prefix}[Permission denied]")
                    return
                
                # Dizinler ve dosyalar ayrı
                dirs = []
                files = []
                
                for entry in entries:
                    if should_ignore(entry):
                        continue
                    
                    full_entry = os.path.join(dir_path, entry)
                    if os.path.isdir(full_entry):
                        dirs.append(entry)
                    else:
                        files.append(entry)
                
                # Önce dizinler
                for i, d in enumerate(dirs):
                    entry_count += 1
                    if entry_count >= self.max_dir_entries:
                        lines.append(f"{prefix}... [truncated]")
                        return
                    
                    is_last = (i == len(dirs) - 1) and not files
                    connector = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{connector}{d}/")
                    
                    # Recurse
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    walk_dir(os.path.join(dir_path, d), new_prefix, depth + 1)
                
                # Sonra dosyalar
                for i, f in enumerate(files):
                    entry_count += 1
                    if entry_count >= self.max_dir_entries:
                        lines.append(f"{prefix}... [truncated]")
                        return
                    
                    is_last = i == len(files) - 1
                    connector = "└── " if is_last else "├── "
                    
                    # File size
                    try:
                        size = os.path.getsize(os.path.join(dir_path, f))
                        size_str = self._format_size(size)
                        lines.append(f"{prefix}{connector}{f} ({size_str})")
                    except:
                        lines.append(f"{prefix}{connector}{f}")
            
            # Root dizin
            lines.append(f"{path.name}/")
            walk_dir(str(path), "", 0)
            
            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={"entry_count": entry_count}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list directory: {str(e)}"
            )
    
    def _smart_truncate(self, text: str) -> str:
        """Akıllı truncation"""
        if len(text) <= self.max_file_chars:
            return text
        
        half = self.max_file_chars // 2
        truncated = len(text) - self.max_file_chars
        
        return (
            text[:half] +
            f"\n\n... [{truncated:,} characters truncated] ...\n\n" +
            text[-half:]
        )
    
    def _format_size(self, size: int) -> str:
        """Human readable file size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}" if unit != "B" else f"{size}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class StrReplaceTool(Tool):
    """
    String replacement tool - atomic file editing
    
    Bu tool, Claude Code'un en akıllı tool'u. Dosyalarda hassas düzenlemeler
    yapmak için kullanılır. old_str dosyada unique olmalı.
    
    Neden write_file değil?
    1. Unique string zorunluluğu = yanlış yere yazma riski yok
    2. Partial edit = tüm dosyayı yeniden yazmak gerekmiyor
    3. Deterministic = aynı input her zaman aynı output verir
    4. Git-friendly = küçük, anlamlı diff'ler
    """
    
    name = "str_replace"
    description = """Replace a unique string in a file with another string.

IMPORTANT:
- The old_str must appear EXACTLY ONCE in the file
- Include enough context (surrounding lines) to make the string unique
- Use this for precise edits rather than rewriting entire files
- To delete text, provide an empty new_str

If the string is not found or appears multiple times, the operation will fail.
In that case, use the view tool to see the exact content and try again with more context.

Tips for making strings unique:
- Include the line above and/or below
- Include unique variable names or comments
- Use enough whitespace to match exactly"""
    
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit"
            },
            "old_str": {
                "type": "string",
                "description": "The exact string to replace (must be unique in file)"
            },
            "new_str": {
                "type": "string",
                "description": "The replacement string (empty to delete)",
                "default": ""
            }
        },
        "required": ["path", "old_str"]
    }
    
    def __init__(
        self,
        working_dir: str = ".",
        create_backup: bool = True,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.create_backup = create_backup

    def _validate_path(self, path: Path) -> None:
        """
        Validate path for security (prevent path traversal).

        Raises:
            PathTraversalError: If path escapes working directory
        """
        try:
            resolved_path = path.resolve(strict=False)
            resolved_path.relative_to(self.working_dir)
        except ValueError:
            logger.warning(
                "path_traversal_attempt",
                path=str(path),
                working_dir=str(self.working_dir),
            )
            raise PathTraversalError(
                message="Path traversal attempt detected",
                path=str(path),
            )
    
    async def execute(
        self,
        path: str,
        old_str: str,
        new_str: str = ""
    ) -> ToolResult:
        """
        String replacement yap
        
        Args:
            path: Dosya yolu
            old_str: Değiştirilecek string (unique olmalı)
            new_str: Yeni string (boş = silme)
            
        Returns:
            ToolResult: İşlem sonucu
        """
        # Path'i resolve et
        if not os.path.isabs(path):
            full_path = os.path.join(self.working_dir, path)
        else:
            full_path = path
        
        full_path = os.path.abspath(full_path)
        
        # Dosya var mı?
        if not os.path.exists(full_path):
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {path}"
            )
        
        try:
            # Dosyayı oku
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Uniqueness check
            count = content.count(old_str)
            
            if count == 0:
                # String bulunamadı - yardımcı bilgi ver
                # En yakın eşleşmeyi bul (fuzzy)
                similar = self._find_similar(content, old_str)
                
                error_msg = f"String not found in file. Make sure you're using the exact string including all whitespace and newlines."
                if similar:
                    error_msg += f"\n\nDid you mean:\n```\n{similar}\n```"
                
                return ToolResult(
                    success=False,
                    output="",
                    error=error_msg
                )
            
            if count > 1:
                # String birden fazla kez var
                # Hangi satırlarda olduğunu göster
                lines_with_match = []
                for i, line in enumerate(content.split("\n"), 1):
                    if old_str in line or (old_str.split("\n")[0] if "\n" in old_str else "") in line:
                        lines_with_match.append(i)
                
                return ToolResult(
                    success=False,
                    output="",
                    error=f"String appears {count} times in the file (around lines: {lines_with_match[:5]}). "
                          f"It must be unique. Add more surrounding context to make it unique."
                )
            
            # Backup oluştur
            if self.create_backup:
                backup_path = full_path + ".bak"
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(content)
            
            # Replacement yap
            new_content = content.replace(old_str, new_str, 1)
            
            # Dosyayı yaz
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            # Diff oluştur (kısa)
            old_lines = old_str.count("\n") + 1
            new_lines = new_str.count("\n") + 1 if new_str else 0
            
            action = "deleted" if not new_str else "replaced"
            
            return ToolResult(
                success=True,
                output=f"Successfully {action} {old_lines} line(s) with {new_lines} line(s) in {path}",
                metadata={
                    "old_lines": old_lines,
                    "new_lines": new_lines,
                    "chars_removed": len(old_str),
                    "chars_added": len(new_str),
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to edit file: {str(e)}"
            )
    
    def _find_similar(self, content: str, search: str, max_chars: int = 200) -> Optional[str]:
        """
        En yakın eşleşmeyi bul - hata mesajları için
        
        Basit bir fuzzy matching - production'da daha sofistike olabilir
        """
        # İlk satırı ara
        first_line = search.split("\n")[0].strip()
        if not first_line:
            return None
        
        for line in content.split("\n"):
            if first_line[:20] in line:
                # Context ile birlikte döndür
                idx = content.find(line)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(line) + 50)
                return content[start:end]
        
        return None


class CreateFileTool(Tool):
    """
    File creation tool
    
    Yeni dosya oluşturur. Mevcut dosyaları overwrite etmez (güvenlik).
    """
    
    name = "create_file"
    description = """Create a new file with the specified content.

Use this tool to:
- Create new source files
- Create configuration files
- Create documentation

The file will be created with the exact content provided.
If the file already exists, the operation will fail (use str_replace to edit existing files).
Parent directories will be created if they don't exist."""
    
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path for the new file"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            },
            "overwrite": {
                "type": "boolean",
                "description": "Whether to overwrite if file exists (default: false)",
                "default": False
            }
        },
        "required": ["path", "content"]
    }
    
    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    def _validate_path(self, path: Path) -> None:
        """
        Validate path for security (prevent path traversal).

        Raises:
            PathTraversalError: If path escapes working directory
        """
        try:
            resolved_path = path.resolve(strict=False)
            resolved_path.relative_to(self.working_dir)
        except ValueError:
            logger.warning(
                "path_traversal_attempt",
                path=str(path),
                working_dir=str(self.working_dir),
            )
            raise PathTraversalError(
                message="Path traversal attempt detected",
                path=str(path),
            )
    
    async def execute(
        self,
        path: str,
        content: str,
        overwrite: bool = False
    ) -> ToolResult:
        """
        Yeni dosya oluştur

        Args:
            path: Dosya yolu
            content: Dosya içeriği
            overwrite: Varsa üzerine yaz

        Returns:
            ToolResult: İşlem sonucu
        """
        logger.debug("tool_execute_start", tool="create_file", path=path)

        # Path'i resolve et
        if Path(path).is_absolute():
            full_path = Path(path)
        else:
            full_path = self.working_dir / path

        full_path = full_path.resolve()

        # Security check
        try:
            self._validate_path(full_path)
        except PathTraversalError as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
        
        # Dosya var mı?
        if os.path.exists(full_path) and not overwrite:
            return ToolResult(
                success=False,
                output="",
                error=f"File already exists: {path}. Use str_replace to edit or set overwrite=true."
            )
        
        try:
            # Parent dizinleri oluştur
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Dosyayı yaz
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            lines = content.count("\n") + 1
            
            return ToolResult(
                success=True,
                output=f"Created {path} ({lines} lines, {len(content)} characters)",
                metadata={
                    "lines": lines,
                    "characters": len(content),
                    "path": full_path,
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to create file: {str(e)}"
            )


class GitTool(Tool):
    """
    Git operations tool for version control

    Provides safe read-only git operations (status, diff, log, blame).
    Write operations (commit, push) should use bash tool.
    """

    name = "git"
    description = """Execute git commands for version control operations.

SAFE OPERATIONS (use this tool):
- git status - Show working tree status
- git diff [file] - Show changes
- git log [options] - Show commit history
- git blame <file> - Show who changed each line
- git show <commit> - Show commit details

WRITE OPERATIONS (use bash tool instead):
- git commit, git push, git pull, git add

EXAMPLES:
  {"name": "git", "arguments": {"command": "status"}}
  {"name": "git", "arguments": {"command": "log", "args": "--oneline -10"}}
  {"name": "git", "arguments": {"command": "blame", "args": "src/main.py"}}
"""

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Git subcommand (status, diff, log, blame, show)",
                "enum": ["status", "diff", "log", "blame", "show"]
            },
            "args": {
                "type": "string",
                "description": "Additional arguments for the command",
                "default": ""
            }
        },
        "required": ["command"]
    }

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    async def execute(self, command: str, args: str = "") -> ToolResult:
        """Execute git command"""
        try:
            full_command = f"git {command} {args}".strip()

            # Use bash tool internally for actual execution
            bash = BashTool(working_dir=self.working_dir)
            result = await bash.execute(full_command)

            return result

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Git command failed: {str(e)}"
            )


class SearchTool(Tool):
    """
    Semantic code search tool

    Better than simple grep - understands context and finds relevant code.
    """

    name = "search"
    description = """Search codebase semantically for relevant code.

Better than grep because it:
- Understands context
- Ranks results by relevance
- Shows code snippets with context

EXAMPLES:
  {"name": "search", "arguments": {"query": "authentication logic"}}
  {"name": "search", "arguments": {"query": "database connection setup"}}
  {"name": "search", "arguments": {"query": "error handling"}}
"""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (natural language or keywords)"
            },
            "file_pattern": {
                "type": "string",
                "description": "Optional file pattern to limit search (e.g., '*.py')",
                "default": "*.py"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5
            }
        },
        "required": ["query"]
    }

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    async def execute(
        self,
        query: str,
        file_pattern: str = "*.py",
        max_results: int = 5
    ) -> ToolResult:
        """Search codebase semantically"""
        try:
            from pathlib import Path
            import re

            # Get keywords from query
            keywords = [k.lower() for k in re.findall(r'\w+', query)]

            results = []
            search_dir = Path(self.working_dir)

            # Search Python files
            for file_path in search_dir.rglob(file_pattern):
                if file_path.is_file():
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='replace')
                        content_lower = content.lower()

                        # Calculate relevance score
                        matches = sum(1 for k in keywords if k in content_lower)
                        relevance = matches / len(keywords) if keywords else 0

                        if relevance >= 0.3:  # 30% keyword match threshold
                            # Get relevant snippet
                            snippet = self._get_relevant_snippet(content, keywords)

                            results.append({
                                "file": str(file_path.relative_to(search_dir)),
                                "relevance": relevance,
                                "snippet": snippet
                            })
                    except Exception:
                        continue

            # Sort by relevance
            results.sort(key=lambda x: x["relevance"], reverse=True)
            results = results[:max_results]

            if not results:
                return ToolResult(
                    success=True,
                    output=f"No results found for: {query}"
                )

            # Format output
            output_lines = [f"Found {len(results)} results for: {query}\n"]
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. {r['file']} ({r['relevance']:.0%} match)")
                output_lines.append(f"   {r['snippet']}")
                output_lines.append("")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={"results_count": len(results)}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Search failed: {str(e)}"
            )

    def _get_relevant_snippet(self, content: str, keywords: list[str]) -> str:
        """Extract relevant snippet from content"""
        lines = content.split('\n')

        # Find line with most keyword matches
        best_line_idx = 0
        best_score = 0

        for i, line in enumerate(lines):
            line_lower = line.lower()
            score = sum(1 for k in keywords if k in line_lower)
            if score > best_score:
                best_score = score
                best_line_idx = i

        # Get context around best line (±2 lines)
        start = max(0, best_line_idx - 1)
        end = min(len(lines), best_line_idx + 2)
        snippet_lines = lines[start:end]

        return '\n   '.join(snippet_lines[:3])  # Max 3 lines


class AstAnalysisTool(Tool):
    """
    Python AST (Abstract Syntax Tree) analysis tool

    Analyzes Python code structure - finds classes, functions, imports, etc.
    """

    name = "ast_analysis"
    description = """Analyze Python code structure using AST.

Extracts:
- Classes and their methods
- Functions and their signatures
- Imports
- Global variables
- Decorators

EXAMPLES:
  {"name": "ast_analysis", "arguments": {"path": "src/main.py"}}
  {"name": "ast_analysis", "arguments": {"path": "src/core/agent.py", "include_docstrings": true}}
"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to Python file to analyze"
            },
            "include_docstrings": {
                "type": "boolean",
                "description": "Include function/class docstrings in output",
                "default": False
            }
        },
        "required": ["path"]
    }

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    async def execute(self, path: str, include_docstrings: bool = False) -> ToolResult:
        """Analyze Python file structure"""
        try:
            import ast
            from pathlib import Path

            file_path = Path(self.working_dir) / path

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}"
                )

            if not file_path.suffix == '.py':
                return ToolResult(
                    success=False,
                    output="",
                    error="Only Python files (.py) can be analyzed"
                )

            # Parse Python file
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content, filename=str(file_path))

            # Extract structure
            structure = {
                "imports": [],
                "classes": [],
                "functions": [],
                "global_vars": []
            }

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        structure["imports"].append(alias.name)

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        structure["imports"].append(f"{module}.{alias.name}")

                elif isinstance(node, ast.ClassDef):
                    class_info = {
                        "name": node.name,
                        "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                        "line": node.lineno
                    }
                    if include_docstrings:
                        class_info["docstring"] = ast.get_docstring(node)
                    structure["classes"].append(class_info)

                elif isinstance(node, ast.FunctionDef):
                    # Only top-level functions (not methods)
                    if isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                        func_info = {
                            "name": node.name,
                            "args": [arg.arg for arg in node.args.args],
                            "line": node.lineno
                        }
                        if include_docstrings:
                            func_info["docstring"] = ast.get_docstring(node)
                        structure["functions"].append(func_info)

                elif isinstance(node, ast.Assign):
                    # Global variables
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            structure["global_vars"].append(target.id)

            # Format output
            output_lines = [f"Structure of {path}:\n"]

            if structure["imports"]:
                output_lines.append(f"Imports ({len(structure['imports'])}):")
                for imp in structure["imports"][:10]:  # Limit to 10
                    output_lines.append(f"  - {imp}")
                if len(structure["imports"]) > 10:
                    output_lines.append(f"  ... and {len(structure['imports']) - 10} more")
                output_lines.append("")

            if structure["classes"]:
                output_lines.append(f"Classes ({len(structure['classes'])}):")
                for cls in structure["classes"]:
                    output_lines.append(f"  - {cls['name']} (line {cls['line']})")
                    output_lines.append(f"    Methods: {', '.join(cls['methods'][:5])}")
                    if include_docstrings and cls.get("docstring"):
                        output_lines.append(f"    Doc: {cls['docstring'][:100]}")
                output_lines.append("")

            if structure["functions"]:
                output_lines.append(f"Functions ({len(structure['functions'])}):")
                for func in structure["functions"]:
                    args_str = ', '.join(func['args'])
                    output_lines.append(f"  - {func['name']}({args_str}) (line {func['line']})")
                    if include_docstrings and func.get("docstring"):
                        output_lines.append(f"    Doc: {func['docstring'][:100]}")
                output_lines.append("")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=structure
            )

        except SyntaxError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Python syntax error: {str(e)}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"AST analysis failed: {str(e)}"
            )


class TestGeneratorTool(Tool):
    """
    Automatic test generator tool

    Generates pytest test templates for Python code.
    """

    name = "generate_tests"
    description = """Generate pytest test templates for Python code.

Creates basic test structure with:
- Test fixtures
- Test cases for each function/method
- Mocking suggestions
- TODO comments for manual completion

EXAMPLES:
  {"name": "generate_tests", "arguments": {"path": "src/utils.py"}}
  {"name": "generate_tests", "arguments": {"path": "src/core/agent.py", "output_path": "tests/test_agent.py"}}
"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to Python file to generate tests for"
            },
            "output_path": {
                "type": "string",
                "description": "Optional output path for test file (default: tests/test_<filename>.py)"
            }
        },
        "required": ["path"]
    }

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    async def execute(self, path: str, output_path: str = None) -> ToolResult:
        """Generate test template"""
        try:
            import ast
            from pathlib import Path

            file_path = Path(self.working_dir) / path

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}"
                )

            # Parse Python file
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content, filename=str(file_path))

            # Extract functions and classes
            functions = []
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                    functions.append({
                        "name": node.name,
                        "args": [arg.arg for arg in node.args.args]
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    classes.append({
                        "name": node.name,
                        "methods": methods
                    })

            # Generate test code
            test_code = self._generate_test_code(file_path.stem, functions, classes)

            # Determine output path
            if not output_path:
                tests_dir = Path(self.working_dir) / "tests"
                tests_dir.mkdir(exist_ok=True)
                output_path = f"tests/test_{file_path.stem}.py"

            output_file = Path(self.working_dir) / output_path
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(test_code, encoding='utf-8')

            return ToolResult(
                success=True,
                output=f"Generated test template: {output_path}\n\nContains:\n- {len(functions)} function tests\n- {len(classes)} class tests\n\nEdit the file to add assertions and complete TODOs.",
                metadata={
                    "output_path": str(output_file),
                    "functions": len(functions),
                    "classes": len(classes)
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Test generation failed: {str(e)}"
            )

    def _generate_test_code(
        self,
        module_name: str,
        functions: list,
        classes: list
    ) -> str:
        """Generate pytest test code"""
        lines = [
            '"""',
            f'Tests for {module_name}',
            '',
            'Auto-generated test template.',
            'TODO: Add assertions and complete test cases.',
            '"""',
            'import pytest',
            f'from src.{module_name} import *',
            '',
            ''
        ]

        # Generate function tests
        for func in functions:
            if func["name"].startswith("_"):
                continue  # Skip private functions

            lines.append(f'def test_{func["name"]}():')
            lines.append(f'    """Test {func["name"]} function"""')

            # Create mock call
            args = ", ".join([f'{arg}=None' for arg in func["args"]])
            lines.append(f'    # TODO: Set up test data')
            lines.append(f'    result = {func["name"]}({args})')
            lines.append(f'    # TODO: Add assertions')
            lines.append(f'    assert result is not None')
            lines.append('')
            lines.append('')

        # Generate class tests
        for cls in classes:
            lines.append(f'class Test{cls["name"]}:')
            lines.append(f'    """Tests for {cls["name"]} class"""')
            lines.append('')
            lines.append('    @pytest.fixture')
            lines.append(f'    def {cls["name"].lower()}(self):')
            lines.append(f'        """Fixture for {cls["name"]} instance"""')
            lines.append(f'        # TODO: Create and configure instance')
            lines.append(f'        return {cls["name"]}()')
            lines.append('')

            for method in cls["methods"]:
                if method.startswith("_") and method != "__init__":
                    continue  # Skip private methods

                lines.append(f'    def test_{method}(self, {cls["name"].lower()}):')
                lines.append(f'        """Test {method} method"""')
                lines.append(f'        # TODO: Set up test data')
                lines.append(f'        # TODO: Call method and add assertions')
                lines.append(f'        pass')
                lines.append('')

            lines.append('')

        return '\n'.join(lines)


def create_default_tools(working_dir: str = ".") -> ToolRegistry:
    """
    Default tool set oluştur

    Bu function, Claude Code benzeri temel tool setini oluşturur.

    Args:
        working_dir: Çalışma dizini

    Returns:
        ToolRegistry: Kayıtlı tool'lar
    """
    registry = ToolRegistry()

    # Core tools
    registry.register(BashTool(working_dir=working_dir))
    registry.register(ViewTool(working_dir=working_dir))
    registry.register(StrReplaceTool(working_dir=working_dir))
    registry.register(CreateFileTool(working_dir=working_dir))

    # New enhanced tools
    registry.register(GitTool(working_dir=working_dir))
    registry.register(SearchTool(working_dir=working_dir))
    registry.register(AstAnalysisTool(working_dir=working_dir))
    registry.register(TestGeneratorTool(working_dir=working_dir))

    return registry
