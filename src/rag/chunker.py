"""
Code Chunker - Smart Code Splitting
====================================

Split codebase into meaningful chunks for embedding.

Strategy:
- Function-level chunks (best granularity)
- Class-level chunks (with methods)
- Module docstrings
- Preserve context (imports, decorators)

Author: Mustafa (Kardelen Yazılım)
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict
import hashlib


@dataclass
class Chunk:
    """
    Code chunk with metadata

    Represents a semantically meaningful piece of code.
    """
    content: str
    file_path: str
    chunk_type: str  # "function", "class", "method", "module"
    name: str
    line_start: int
    line_end: int

    # Optional metadata
    docstring: Optional[str] = None
    imports: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)

    # Computed fields
    hash: Optional[str] = None

    def __post_init__(self):
        """Compute hash after initialization"""
        if self.hash is None:
            self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Compute content hash for change detection"""
        return hashlib.sha256(self.content.encode()).hexdigest()

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "content": self.content,
            "file_path": self.file_path,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "docstring": self.docstring,
            "imports": self.imports,
            "decorators": self.decorators,
            "calls": self.calls,
            "hash": self.hash,
        }


class CodeChunker:
    """
    Smart code chunker using AST

    Splits Python code into function/class-level chunks.
    """

    def __init__(self, max_chunk_size: int = 1000):
        self.max_chunk_size = max_chunk_size

    def chunk_file(self, file_path: Path) -> List[Chunk]:
        """
        Chunk a Python file

        Args:
            file_path: Path to Python file

        Returns:
            List of Chunk objects
        """
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content, filename=str(file_path))
            lines = content.split('\n')

            chunks = []

            # Extract module-level docstring
            module_doc = ast.get_docstring(tree)
            if module_doc:
                chunks.append(Chunk(
                    content=module_doc,
                    file_path=str(file_path),
                    chunk_type="module",
                    name=file_path.stem,
                    line_start=1,
                    line_end=len(module_doc.split('\n')),
                    docstring=module_doc
                ))

            # Extract imports
            imports = self._extract_imports(tree)

            # Process top-level nodes
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef):
                    chunk = self._chunk_function(node, lines, file_path, imports)
                    if chunk:
                        chunks.append(chunk)

                elif isinstance(node, ast.ClassDef):
                    class_chunk = self._chunk_class(node, lines, file_path, imports)
                    if class_chunk:
                        chunks.append(class_chunk)

            return chunks

        except Exception as e:
            # Return empty list on error (file might not be valid Python)
            return []

    def _extract_imports(self, tree: ast.Module) -> List[str]:
        """Extract import statements"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        return imports

    def _chunk_function(
        self,
        node: ast.FunctionDef,
        lines: List[str],
        file_path: Path,
        imports: List[str]
    ) -> Optional[Chunk]:
        """Create chunk from function definition"""
        try:
            # Get function source
            start_line = node.lineno - 1  # 0-indexed
            end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 1

            content = '\n'.join(lines[start_line:end_line])

            # Don't chunk if too small or too large
            if len(content) < 10 or len(content) > self.max_chunk_size:
                return None

            # Extract decorators
            decorators = [ast.unparse(d) for d in node.decorator_list]

            # Extract function calls (simplified)
            calls = self._extract_calls(node)

            return Chunk(
                content=content,
                file_path=str(file_path),
                chunk_type="function",
                name=node.name,
                line_start=node.lineno,
                line_end=end_line + 1,
                docstring=ast.get_docstring(node),
                imports=imports,
                decorators=decorators,
                calls=calls
            )

        except Exception:
            return None

    def _chunk_class(
        self,
        node: ast.ClassDef,
        lines: List[str],
        file_path: Path,
        imports: List[str]
    ) -> Optional[Chunk]:
        """Create chunk from class definition"""
        try:
            start_line = node.lineno - 1
            end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 1

            content = '\n'.join(lines[start_line:end_line])

            # Don't chunk if too large (split methods instead)
            if len(content) > self.max_chunk_size:
                return None

            # Extract decorators
            decorators = [ast.unparse(d) for d in node.decorator_list]

            # Extract method names
            methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]

            return Chunk(
                content=content,
                file_path=str(file_path),
                chunk_type="class",
                name=node.name,
                line_start=node.lineno,
                line_end=end_line + 1,
                docstring=ast.get_docstring(node),
                imports=imports,
                decorators=decorators,
                calls=methods  # Methods as "calls"
            )

        except Exception:
            return None

    def _extract_calls(self, node: ast.AST) -> List[str]:
        """Extract function calls from node"""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return list(set(calls))[:10]  # Limit to 10 unique calls


def chunk_codebase(
    root_dir: Path,
    file_pattern: str = "**/*.py",
    max_chunk_size: int = 1000
) -> List[Chunk]:
    """
    Chunk entire codebase

    Args:
        root_dir: Root directory to scan
        file_pattern: Glob pattern for files
        max_chunk_size: Maximum chunk size in characters

    Returns:
        List of all chunks
    """
    chunker = CodeChunker(max_chunk_size=max_chunk_size)
    all_chunks = []

    for file_path in root_dir.glob(file_pattern):
        if file_path.is_file():
            # Skip test files, __pycache__, etc.
            if any(x in str(file_path) for x in ['__pycache__', '.pyc', 'test_']):
                continue

            chunks = chunker.chunk_file(file_path)
            all_chunks.extend(chunks)

    return all_chunks
