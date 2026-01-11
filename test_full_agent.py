"""
End-to-end test for the agent
"""
import asyncio
import os
import shutil
from pathlib import Path
from src.core.agent import Agent, AgentConfig
from src.core.providers import create_provider
from src.core.tools import create_default_tools

async def test_agent():
    """Test the full agent flow"""
    print("=" * 80)
    print("Full Agent Test - Create Folder and File")
    print("=" * 80)

    # Clean up test directories if they exist
    test_dirs = ["ahmet mehmet", "test_folder"]
    for d in test_dirs:
        if Path(d).exists():
            shutil.rmtree(d)
            print(f"Cleaned up existing {d}")

    # Create agent
    config = AgentConfig(
        model_name="qwen2.5-coder:7b",
        working_dir=os.getcwd(),
        max_iterations=10,
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

    print(f"\n[OK] Agent created")
    print(f"[OK] Working dir: {os.getcwd()}")

    # Test prompt
    prompt = 'Bir klasor olustur adi "ahmet mehmet" olsun icinde bir text dosyasi olustur icine de "sifre:Haho" yazsin'

    print(f"\n[TASK] {prompt}")
    print("\n" + "=" * 80)

    # Run agent
    iteration = 0
    async for response in agent.run(prompt):
        iteration += 1
        print(f"\n[Iteration {iteration}]")

        if response.content:
            print(f"Content: {response.content[:200]}...")

        if response.tool_calls:
            print(f"Tool calls: {len(response.tool_calls)}")
            for tc in response.tool_calls:
                print(f"  - {tc.get('name')}: {tc.get('arguments')}")

        if response.tool_results:
            print(f"Tool results: {len(response.tool_results)}")
            for i, tr in enumerate(response.tool_results):
                status = "[OK]" if tr.success else "[FAIL]"
                output_preview = tr.output[:100] if tr.output else tr.error
                print(f"  {status} Result {i+1}: {output_preview}")

        if response.state.value == "completed":
            print("\n[OK] Agent completed!")
            break

        if response.state.value == "error":
            print("\n[FAIL] Agent error!")
            break

    # Verify results
    print("\n" + "=" * 80)
    print("Verification")
    print("=" * 80)

    folder_path = Path("ahmet mehmet")
    file_path = folder_path / "sifre.txt"

    if folder_path.exists():
        print(f"[OK] Folder created: {folder_path}")
    else:
        print(f"[FAIL] Folder NOT created: {folder_path}")

    if file_path.exists():
        print(f"[OK] File created: {file_path}")
        content = file_path.read_text(encoding="utf-8")
        if "sifre:Haho" in content:
            print(f"[OK] File content correct: {content}")
        else:
            print(f"[FAIL] File content wrong: {content}")
    else:
        print(f"[FAIL] File NOT created: {file_path}")

    # Cleanup
    await provider.close()

    print("\n" + "=" * 80)
    print("Test completed")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_agent())
