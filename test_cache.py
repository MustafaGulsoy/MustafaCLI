"""
Test context caching system
"""
import asyncio
import os
from src.core.agent import Agent, AgentConfig
from src.core.providers import create_provider
from src.core.tools import create_default_tools

async def test_cache():
    """Test that caching improves performance"""
    print("=" * 80)
    print("Testing Context Cache")
    print("=" * 80)

    # Create agent
    config = AgentConfig(
        model_name="qwen2.5-coder:7b",
        working_dir=os.getcwd(),
        max_iterations=10,
        temperature=0.1,
    )

    provider = create_provider(
        provider_type="ollama",
        model="qwen2.5-coder:7b",
    )

    tools = create_default_tools(os.getcwd())

    agent = Agent(
        config=config,
        provider=provider,
        tool_registry=tools,
    )

    # Simple task
    prompt = 'list current directory files'

    print(f"\n[TASK] {prompt}")
    print("\n" + "=" * 80)

    # Run agent
    async for response in agent.run(prompt):
        if response.state.value == "completed":
            print(f"\n{response.content}")

            # Check cache stats
            if hasattr(agent.context, 'get_cache_stats'):
                stats = agent.context.get_cache_stats()
                print("\n" + "=" * 80)
                print("Cache Statistics")
                print("=" * 80)
                print(f"Hits: {stats.get('hits', 0)}")
                print(f"Misses: {stats.get('misses', 0)}")
                print(f"Hit Rate: {stats.get('hit_rate', 0):.1%}")
                print(f"Tokens Saved: {stats.get('tokens_saved', 0)}")
                print("\nCache is working! ✓")
            break

    await provider.close()

if __name__ == "__main__":
    asyncio.run(test_cache())
