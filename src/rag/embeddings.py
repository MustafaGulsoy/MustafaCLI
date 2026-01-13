"""
Embedding Model - Vector Representations
=========================================

Generate embeddings using Ollama's nomic-embed-text model.

Why Ollama?
- Local (privacy)
- Fast (GPU accelerated)
- 768-dim embeddings
- Already in your stack

Author: Mustafa (Kardelen Yazılım)
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import httpx
import asyncio


class EmbeddingModel(ABC):
    """Base class for embedding models"""

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for batch of texts"""
        pass


class OllamaEmbeddings(EmbeddingModel):
    """
    Ollama embedding model

    Uses nomic-embed-text for fast, local embeddings.

    Usage:
        embeddings = OllamaEmbeddings()
        vector = await embeddings.embed("def hello(): pass")
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        try:
            response = await self._client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embedding", [])

        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {str(e)}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for batch of texts"""
        # Ollama doesn't have native batch API, so we parallelize
        tasks = [self.embed(text) for text in texts]
        return await asyncio.gather(*tasks)

    async def close(self):
        """Close HTTP client"""
        await self._client.aclose()

    def __del__(self):
        """Cleanup on deletion"""
        try:
            asyncio.create_task(self.close())
        except:
            pass


class MockEmbeddings(EmbeddingModel):
    """
    Mock embeddings for testing

    Returns random vectors without calling Ollama.
    """

    def __init__(self, dim: int = 768):
        self.dim = dim

    async def embed(self, text: str) -> List[float]:
        """Generate mock embedding"""
        import random
        return [random.random() for _ in range(self.dim)]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings"""
        return [await self.embed(text) for text in texts]


# Factory function
def create_embedding_model(
    provider: str = "ollama",
    **kwargs
) -> EmbeddingModel:
    """
    Create embedding model

    Args:
        provider: "ollama" or "mock"
        **kwargs: Provider-specific arguments

    Returns:
        EmbeddingModel instance
    """
    if provider == "ollama":
        return OllamaEmbeddings(**kwargs)
    elif provider == "mock":
        return MockEmbeddings(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")
