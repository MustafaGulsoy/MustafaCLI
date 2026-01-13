"""
RAG (Retrieval Augmented Generation) Module
============================================

Provides semantic code search and retrieval for the agent.

Components:
- Embeddings: Generate vector embeddings using Ollama
- Chunker: Split code into meaningful chunks
- Indexer: Build and maintain vector database
- Retriever: Search and rank relevant code
- Integration: Connect RAG with Agent

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from .embeddings import EmbeddingModel, OllamaEmbeddings
from .chunker import CodeChunker, Chunk
from .indexer import CodebaseIndexer
from .retriever import CodeRetriever, SearchResult
from .integration import RAGAgent, RAGConfig

__all__ = [
    "EmbeddingModel",
    "OllamaEmbeddings",
    "CodeChunker",
    "Chunk",
    "CodebaseIndexer",
    "CodeRetriever",
    "SearchResult",
    "RAGAgent",
    "RAGConfig",
]

__version__ = "0.1.0"
