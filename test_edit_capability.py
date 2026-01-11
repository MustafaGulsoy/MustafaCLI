"""
Test file editing capability with improved prompts
"""
import asyncio
import os
from pathlib import Path
from src.core.agent import Agent, AgentConfig
from src.core.providers import create_provider
from src.core.tools import create_default_tools

async def test_file_edit():
    """Test if agent can edit files now"""
    print("=" * 80)
    print("Testing File Editing Capability")
    print("=" * 80)

    # Create a test file
    test_file = Path("test_user.py")
    test_file.write_text('name = "John"\nage = 25\n', encoding="utf-8")
    print(f"\n[OK] Created test file with content:")
    print(test_file.read_text())

    # Create agent
    config = AgentConfig(
        model_name="qwen2.5-coder:7b",
        working_dir=os.getcwd(),
        max_iterations=10,
        temperature=0.1,  # More deterministic
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

    # Test prompt - edit the file
    prompt = 'test_user.py dosyasindaki "John" ismini "Jane" olarak degistir'

    print(f"\n[TASK] {prompt}")
    print("\n" + "=" * 80)

    # Run agent
    iteration = 0
    async for response in agent.run(prompt):
        iteration += 1
        print(f"\n[Iteration {iteration}]")

        if response.tool_calls:
            print(f"Tool calls: {len(response.tool_calls)}")
            for tc in response.tool_calls:
                print(f"  - {tc.get('name')}: {tc.get('arguments')}")

        if response.tool_results:
            for i, tr in enumerate(response.tool_results):
                status = "[OK]" if tr.success else "[FAIL]"
                print(f"  {status} {tr.output[:150]}")
                if tr.error:
                    print(f"       Error: {tr.error}")

        if response.state.value == "completed":
            print("\n[OK] Agent completed!")
            break

        if response.state.value == "error":
            print("\n[FAIL] Agent error!")
            break

        if iteration > 5:
            print("\n[WARN] Too many iterations, stopping")
            break

    # Verify
    print("\n" + "=" * 80)
    print("Verification")
    print("=" * 80)

    final_content = test_file.read_text()
    print(f"\nFinal content:\n{final_content}")

    if "Jane" in final_content and "John" not in final_content:
        print("\n[SUCCESS] File was edited correctly!")
    else:
        print("\n[FAIL] File was NOT edited correctly")
        print("Expected: name = \"Jane\"")
        print(f"Got: {final_content}")

    # Cleanup
    test_file.unlink()
    await provider.close()

if __name__ == "__main__":
    asyncio.run(test_file_edit())
