"""
RAG Agent Integration
=====================

Connect RAG system with Agent for enhanced context.

Smart Features:
- Automatic RAG trigger detection
- Context injection with retrieved code
- Cache RAG results
- Relevance filtering

Author: Mustafa (Kardelen Yazılım)
"""

from dataclasses import dataclass
from typing import List, Optional, AsyncGenerator
from pathlib import Path

from ..core.agent import Agent, AgentConfig, AgentResponse
from ..core.providers import ModelProvider
from ..core.tools import ToolRegistry

from .retriever import CodeRetriever, SearchResult


@dataclass
class RAGConfig:
    """RAG configuration"""
    enabled: bool = True
    db_path: str = ".rag_db"
    max_results: int = 3  # Top N results to inject
    min_score: float = 0.5  # Minimum relevance threshold
    auto_trigger: bool = True  # Automatically detect when to use RAG
    cache_results: bool = True  # Cache RAG results


class RAGAgent:
    """
    Agent with RAG support

    Enhances base Agent with semantic code search.

    Usage:
        rag_agent = RAGAgent(
            config=agent_config,
            provider=provider,
            tool_registry=tools,
            rag_config=RAGConfig(enabled=True)
        )

        async for response in rag_agent.run("fix bug in tool execution"):
            print(response.content)
    """

    def __init__(
        self,
        config: AgentConfig,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        rag_config: Optional[RAGConfig] = None,
    ):
        self.config = config
        self.provider = provider
        self.tools = tool_registry
        self.rag_config = rag_config or RAGConfig()

        # Base agent
        self.agent = Agent(
            config=config,
            provider=provider,
            tool_registry=tool_registry
        )

        # RAG retriever (initialized lazily)
        self._retriever: Optional[CodeRetriever] = None

        # Cache
        self._rag_cache: dict = {}

    @property
    def retriever(self) -> CodeRetriever:
        """Get or create retriever"""
        if self._retriever is None:
            if not Path(self.rag_config.db_path).exists():
                raise FileNotFoundError(
                    f"RAG database not found at {self.rag_config.db_path}. "
                    "Run indexer first: python -m src.rag.indexer"
                )

            self._retriever = CodeRetriever(db_path=self.rag_config.db_path)

        return self._retriever

    def should_use_rag(self, query: str) -> bool:
        """
        Detect if RAG should be used for this query

        RAG is useful for:
        - Code search ("where is", "find code")
        - Understanding ("how does", "explain")
        - Modification ("fix bug in", "update")
        - Review ("check", "analyze")

        RAG is NOT useful for:
        - Creation ("create new")
        - Simple commands ("list files")
        """
        if not self.rag_config.enabled or not self.rag_config.auto_trigger:
            return self.rag_config.enabled

        query_lower = query.lower()

        # Positive triggers (USE RAG)
        use_triggers = [
            # Search
            "where is", "find", "search", "locate",
            # Understanding
            "how does", "explain", "what is", "show me",
            # Modification
            "fix", "bug", "update", "change", "modify", "improve",
            # Review
            "review", "check", "analyze", "look at",
        ]

        # Negative triggers (DON'T USE RAG)
        skip_triggers = [
            "create new", "write from scratch", "new file",
            "list", "delete", "remove",
        ]

        # Check skip first (higher priority)
        if any(trigger in query_lower for trigger in skip_triggers):
            return False

        # Check use triggers
        if any(trigger in query_lower for trigger in use_triggers):
            return True

        # Default: use RAG for longer queries (likely complex)
        return len(query.split()) > 5

    async def _retrieve_relevant_code(self, query: str) -> List[SearchResult]:
        """Retrieve relevant code chunks"""
        # Check cache
        if self.rag_config.cache_results and query in self._rag_cache:
            return self._rag_cache[query]

        # Retrieve
        results = await self.retriever.search(
            query=query,
            n=self.rag_config.max_results,
            min_score=self.rag_config.min_score
        )

        # Cache
        if self.rag_config.cache_results:
            self._rag_cache[query] = results

        return results

    def _format_rag_context(self, results: List[SearchResult]) -> str:
        """Format RAG results as context"""
        if not results:
            return ""

        lines = [
            "",
            "=" * 80,
            "RELEVANT CODE FROM CODEBASE (provided by RAG):",
            "=" * 80,
            ""
        ]

        for i, result in enumerate(results, 1):
            lines.append(f"{i}. {result.get_location()} - {result.name} ({result.score:.0%} relevant)")
            lines.append(f"   Type: {result.chunk_type}")

            if result.docstring:
                lines.append(f"   Doc: {result.docstring[:150]}")

            lines.append("")
            lines.append("   Code:")
            # Indent code
            for line in result.get_snippet(max_lines=10).split('\n'):
                lines.append(f"   {line}")
            lines.append("")

        lines.append("=" * 80)
        lines.append("")

        return "\n".join(lines)

    async def run(
        self,
        user_input: str,
        *,
        stream: bool = True,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Run agent with RAG support

        Args:
            user_input: User query
            stream: Stream responses

        Yields:
            AgentResponse objects
        """
        # Check if RAG should be used
        use_rag = self.should_use_rag(user_input)

        if use_rag:
            try:
                # Retrieve relevant code
                results = await self._retrieve_relevant_code(user_input)

                if results:
                    # Format as context
                    rag_context = self._format_rag_context(results)

                    # Inject into query
                    enhanced_query = f"{rag_context}\n\nUSER TASK:\n{user_input}"

                    # Show RAG results to user
                    print(f"\n[RAG] Found {len(results)} relevant code chunks")
                    for r in results:
                        print(f"  - {r.get_location()}: {r.name} ({r.score:.0%})")
                    print()

                else:
                    # No relevant code found, use original query
                    enhanced_query = user_input
                    print("[RAG] No relevant code found, proceeding without RAG context\n")

            except Exception as e:
                # RAG failed, fallback to original query
                print(f"[RAG] Error: {str(e)}, proceeding without RAG\n")
                enhanced_query = user_input

        else:
            # Don't use RAG
            enhanced_query = user_input

        # Run base agent with enhanced query
        async for response in self.agent.run(enhanced_query, stream=stream):
            yield response


# Convenience function
def create_rag_agent(
    config: AgentConfig,
    provider: ModelProvider,
    tool_registry: ToolRegistry,
    enable_rag: bool = True,
    rag_db_path: str = ".rag_db",
) -> RAGAgent:
    """
    Create RAG-enabled agent

    Args:
        config: Agent configuration
        provider: Model provider
        tool_registry: Tool registry
        enable_rag: Enable RAG (default: True)
        rag_db_path: RAG database path

    Returns:
        RAGAgent instance
    """
    rag_config = RAGConfig(
        enabled=enable_rag,
        db_path=rag_db_path,
        max_results=3,
        min_score=0.5,
        auto_trigger=True,
        cache_results=True
    )

    return RAGAgent(
        config=config,
        provider=provider,
        tool_registry=tool_registry,
        rag_config=rag_config
    )
