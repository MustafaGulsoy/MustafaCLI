"""
Code Retriever - Semantic Search
=================================

Search vector database for relevant code.

Features:
- Semantic similarity search
- Hybrid ranking (vector + keyword + recency)
- Result filtering and ranking
- Query expansion

Author: Mustafa (Kardelen Yazılım)
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

try:
    import chromadb
except ImportError:
    chromadb = None

from .embeddings import EmbeddingModel, create_embedding_model


@dataclass
class SearchResult:
    """
    Search result with metadata

    Represents a relevant code chunk.
    """
    content: str
    file_path: str
    chunk_type: str
    name: str
    line_start: int
    line_end: int
    score: float  # Relevance score (0-1)

    # Optional metadata
    docstring: Optional[str] = None
    imports: List[str] = None
    decorators: List[str] = None

    def __post_init__(self):
        if self.imports is None:
            self.imports = []
        if self.decorators is None:
            self.decorators = []

    def get_location(self) -> str:
        """Get file:line location"""
        return f"{self.file_path}:{self.line_start}"

    def get_snippet(self, max_lines: int = 5) -> str:
        """Get code snippet (truncated)"""
        lines = self.content.split('\n')
        if len(lines) <= max_lines:
            return self.content

        return '\n'.join(lines[:max_lines]) + '\n...'


class CodeRetriever:
    """
    Semantic code search

    Usage:
        retriever = CodeRetriever(db_path=".rag_db")
        results = await retriever.search("authentication logic", n=5)
    """

    def __init__(
        self,
        db_path: str = ".rag_db",
        collection_name: str = "codebase",
        embedding_model: Optional[EmbeddingModel] = None,
    ):
        if chromadb is None:
            raise ImportError(
                "chromadb not installed. Run: pip install chromadb"
            )

        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(
                f"RAG database not found at {db_path}. Run indexer first."
            )

        # Initialize Chroma client
        self.client = chromadb.PersistentClient(path=str(self.db_path))

        # Get collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
        except:
            raise ValueError(
                f"Collection '{collection_name}' not found. Run indexer first."
            )

        # Embedding model
        self.embeddings = embedding_model or create_embedding_model("ollama")

    async def search(
        self,
        query: str,
        n: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """
        Search for relevant code

        Args:
            query: Search query (natural language or keywords)
            n: Number of results to return
            where: Optional metadata filter (e.g., {"chunk_type": "function"})
            min_score: Minimum relevance score threshold

        Returns:
            List of SearchResult objects
        """
        # Generate query embedding
        query_embedding = await self.embeddings.embed(query)

        # Search vector DB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n * 2,  # Get more, then filter
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        # Convert to SearchResult objects
        search_results = []

        if not results or not results.get('ids'):
            return []

        for i in range(len(results['ids'][0])):
            content = results['documents'][0][i]
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i] if 'distances' in results else 0

            # Convert distance to similarity score (0-1)
            # Cosine distance: 0 (identical) to 2 (opposite)
            score = max(0, 1 - (distance / 2))

            # Apply keyword boost
            score = self._apply_keyword_boost(query, content, score)

            if score >= min_score:
                result = SearchResult(
                    content=content,
                    file_path=metadata.get('file_path', ''),
                    chunk_type=metadata.get('chunk_type', ''),
                    name=metadata.get('name', ''),
                    line_start=metadata.get('line_start', 0),
                    line_end=metadata.get('line_end', 0),
                    score=score,
                    docstring=metadata.get('docstring'),
                    imports=metadata.get('imports', []),
                    decorators=metadata.get('decorators', [])
                )
                search_results.append(result)

        # Sort by score
        search_results.sort(key=lambda x: x.score, reverse=True)

        # Return top N
        return search_results[:n]

    def _apply_keyword_boost(self, query: str, content: str, base_score: float) -> float:
        """
        Boost score if query keywords appear in content

        Hybrid ranking: vector similarity + keyword matching
        """
        query_lower = query.lower()
        content_lower = content.lower()

        # Extract keywords (simple word split)
        keywords = [w for w in query_lower.split() if len(w) > 3]

        if not keywords:
            return base_score

        # Count keyword matches
        matches = sum(1 for kw in keywords if kw in content_lower)
        match_ratio = matches / len(keywords)

        # Boost score by up to 20%
        boost = match_ratio * 0.2

        return min(1.0, base_score + boost)

    async def search_by_file(
        self,
        file_pattern: str,
        n: int = 10
    ) -> List[SearchResult]:
        """
        Search chunks from specific files

        Args:
            file_pattern: File path pattern (e.g., "agent.py", "core/")
            n: Number of results

        Returns:
            List of SearchResult objects
        """
        # Note: Chroma doesn't support regex in where clause
        # We'll filter after retrieval
        results = self.collection.get(
            limit=n * 2,  # Get more, then filter
            include=["documents", "metadatas"]
        )

        search_results = []

        if not results or not results.get('ids'):
            return []

        for i in range(len(results['ids'])):
            metadata = results['metadatas'][i]
            file_path = metadata.get('file_path', '')

            # Check if file matches pattern
            if file_pattern.lower() in file_path.lower():
                result = SearchResult(
                    content=results['documents'][i],
                    file_path=file_path,
                    chunk_type=metadata.get('chunk_type', ''),
                    name=metadata.get('name', ''),
                    line_start=metadata.get('line_start', 0),
                    line_end=metadata.get('line_end', 0),
                    score=1.0,  # No scoring for file search
                    docstring=metadata.get('docstring'),
                    imports=metadata.get('imports', []),
                    decorators=metadata.get('decorators', [])
                )
                search_results.append(result)

        return search_results[:n]

    async def search_by_name(
        self,
        name: str,
        chunk_type: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Search by function/class name

        Args:
            name: Function or class name
            chunk_type: Optional type filter ("function", "class", etc.)

        Returns:
            List of SearchResult objects
        """
        where = {"name": name}
        if chunk_type:
            where["chunk_type"] = chunk_type

        results = self.collection.get(
            where=where,
            include=["documents", "metadatas"]
        )

        search_results = []

        if not results or not results.get('ids'):
            return []

        for i in range(len(results['ids'])):
            metadata = results['metadatas'][i]
            result = SearchResult(
                content=results['documents'][i],
                file_path=metadata.get('file_path', ''),
                chunk_type=metadata.get('chunk_type', ''),
                name=metadata.get('name', ''),
                line_start=metadata.get('line_start', 0),
                line_end=metadata.get('line_end', 0),
                score=1.0,
                docstring=metadata.get('docstring'),
                imports=metadata.get('imports', []),
                decorators=metadata.get('decorators', [])
            )
            search_results.append(result)

        return search_results

    def get_stats(self) -> Dict:
        """Get retriever statistics"""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "db_path": str(self.db_path),
            }
        except Exception as e:
            return {"error": str(e)}


# CLI for testing retrieval
if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Search codebase with RAG")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--db", default=".rag_db", help="Database path")
    parser.add_argument("-n", type=int, default=5, help="Number of results")
    args = parser.parse_args()

    async def main():
        print(f"Searching for: {args.query}\n")

        retriever = CodeRetriever(db_path=args.db)
        results = await retriever.search(args.query, n=args.n)

        if not results:
            print("No results found.")
            return

        print(f"Found {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.get_location()} - {result.name} ({result.score:.2f})")
            print(f"   Type: {result.chunk_type}")
            if result.docstring:
                doc = result.docstring[:100]
                print(f"   Doc: {doc}...")
            print(f"\n   {result.get_snippet(max_lines=3)}\n")

    asyncio.run(main())
