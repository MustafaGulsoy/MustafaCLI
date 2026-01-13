"""
Codebase Indexer - Build Vector Database
=========================================

Index codebase for semantic search.

Process:
1. Scan codebase for Python files
2. Chunk code intelligently
3. Generate embeddings
4. Store in Chroma DB with metadata

Supports incremental indexing (only reindex changed files).

Author: Mustafa (Kardelen Yazılım)
"""

import asyncio
from pathlib import Path
from typing import List, Optional, Dict
import hashlib
import json

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

from .chunker import CodeChunker, Chunk, chunk_codebase
from .embeddings import EmbeddingModel, create_embedding_model


class CodebaseIndexer:
    """
    Index codebase for semantic search

    Usage:
        indexer = CodebaseIndexer(db_path=".rag_db")
        await indexer.index_codebase(".", force=False)
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
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize Chroma client
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Code chunks with embeddings"}
        )

        # Embedding model
        self.embeddings = embedding_model or create_embedding_model("ollama")

        # Track indexed files
        self._index_state_file = self.db_path / "index_state.json"
        self._index_state = self._load_index_state()

    def _load_index_state(self) -> Dict[str, str]:
        """Load index state (file hashes)"""
        if self._index_state_file.exists():
            return json.loads(self._index_state_file.read_text())
        return {}

    def _save_index_state(self):
        """Save index state"""
        self._index_state_file.write_text(json.dumps(self._index_state, indent=2))

    def _file_hash(self, file_path: Path) -> str:
        """Compute file hash for change detection"""
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _needs_reindex(self, file_path: Path) -> bool:
        """Check if file needs reindexing"""
        file_key = str(file_path)
        current_hash = self._file_hash(file_path)
        stored_hash = self._index_state.get(file_key)

        return current_hash != stored_hash

    async def index_codebase(
        self,
        root_dir: str,
        file_pattern: str = "**/*.py",
        force: bool = False,
        max_workers: int = 5,
    ) -> Dict[str, int]:
        """
        Index codebase

        Args:
            root_dir: Root directory to scan
            file_pattern: Glob pattern for files
            force: Force reindex all files
            max_workers: Max concurrent embeddings

        Returns:
            Stats dictionary
        """
        root_path = Path(root_dir)

        stats = {
            "files_scanned": 0,
            "files_indexed": 0,
            "chunks_created": 0,
            "chunks_added": 0,
        }

        # Scan files
        chunker = CodeChunker()
        files_to_index = []

        for file_path in root_path.glob(file_pattern):
            if not file_path.is_file():
                continue

            # Skip unwanted files
            if any(x in str(file_path) for x in ['__pycache__', '.pyc', 'venv', '.git']):
                continue

            stats["files_scanned"] += 1

            # Check if needs reindexing
            if force or self._needs_reindex(file_path):
                files_to_index.append(file_path)

        print(f"Found {stats['files_scanned']} files, {len(files_to_index)} need indexing")

        # Process files
        for file_path in files_to_index:
            try:
                # Chunk file
                chunks = chunker.chunk_file(file_path)
                stats["chunks_created"] += len(chunks)

                if chunks:
                    # Remove old chunks for this file
                    self._remove_file_chunks(str(file_path))

                    # Add new chunks
                    await self._add_chunks(chunks, max_workers=max_workers)
                    stats["chunks_added"] += len(chunks)

                    # Update index state
                    self._index_state[str(file_path)] = self._file_hash(file_path)
                    stats["files_indexed"] += 1

                    print(f"Indexed {file_path.name}: {len(chunks)} chunks")

            except Exception as e:
                print(f"Error indexing {file_path}: {str(e)}")

        # Save index state
        self._save_index_state()

        return stats

    def _remove_file_chunks(self, file_path: str):
        """Remove all chunks for a file"""
        try:
            # Get existing chunks for this file
            results = self.collection.get(
                where={"file_path": file_path}
            )

            if results and results.get('ids'):
                self.collection.delete(ids=results['ids'])

        except Exception as e:
            print(f"Error removing chunks for {file_path}: {str(e)}")

    async def _add_chunks(self, chunks: List[Chunk], max_workers: int = 5):
        """Add chunks to vector DB"""
        if not chunks:
            return

        # Generate embeddings in batches
        texts = [chunk.content for chunk in chunks]

        # Batch processing for efficiency
        batch_size = max_workers
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = await self.embeddings.embed_batch(batch)
            embeddings.extend(batch_embeddings)

        # Prepare data for Chroma
        ids = [f"{chunk.file_path}:{chunk.line_start}" for chunk in chunks]
        metadatas = [chunk.to_dict() for chunk in chunks]

        # Remove 'content' from metadata (stored separately)
        for meta in metadatas:
            meta.pop('content', None)

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

    async def reindex_file(self, file_path: str):
        """Reindex a single file"""
        path = Path(file_path)
        if not path.exists():
            return

        chunker = CodeChunker()
        chunks = chunker.chunk_file(path)

        if chunks:
            self._remove_file_chunks(str(path))
            await self._add_chunks(chunks)
            self._index_state[str(path)] = self._file_hash(path)
            self._save_index_state()

    def get_stats(self) -> Dict:
        """Get indexer statistics"""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "indexed_files": len(self._index_state),
                "db_path": str(self.db_path),
            }
        except:
            return {"error": "Failed to get stats"}

    def clear_index(self):
        """Clear entire index"""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.create_collection(
            name=self.collection.name,
            metadata={"description": "Code chunks with embeddings"}
        )
        self._index_state = {}
        self._save_index_state()


# CLI for manual indexing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Index codebase for RAG")
    parser.add_argument("--path", default=".", help="Path to codebase")
    parser.add_argument("--db", default=".rag_db", help="Database path")
    parser.add_argument("--force", action="store_true", help="Force reindex")
    args = parser.parse_args()

    async def main():
        print(f"Indexing codebase at: {args.path}")
        print(f"Database: {args.db}\n")

        indexer = CodebaseIndexer(db_path=args.db)
        stats = await indexer.index_codebase(
            root_dir=args.path,
            force=args.force
        )

        print("\nIndexing complete!")
        print(f"Files scanned: {stats['files_scanned']}")
        print(f"Files indexed: {stats['files_indexed']}")
        print(f"Chunks created: {stats['chunks_created']}")
        print(f"Chunks added: {stats['chunks_added']}")

        db_stats = indexer.get_stats()
        print(f"\nDatabase stats:")
        print(f"Total chunks: {db_stats['total_chunks']}")
        print(f"Indexed files: {db_stats['indexed_files']}")

    asyncio.run(main())
