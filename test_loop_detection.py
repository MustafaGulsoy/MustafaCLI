"""
Test loop detection with repeated failures
"""
import asyncio
import os
from pathlib import Path
from src.core.agent import Agent, AgentConfig
from src.core.providers import create_provider
from src.core.tools import create_default_tools

async def test_loop_detection():
    """Test that agent stops after repeated failures"""
    print("=" * 80)
    print("Testing Loop Detection")
    print("=" * 80)

    # Create test folder with space in name
    test_folder = Path("ahmet mehmet")
    test_folder.mkdir(exist_ok=True)
    test_file = test_folder / "sifre.txt"
    test_file.write_text("Test content\n", encoding="utf-8")

    print(f"\n[OK] Created folder: '{test_folder}'")
    print(f"[OK] Created file: '{test_file}'")

    # Create agent
    config = AgentConfig(
        model_name="qwen2.5-coder:7b",
        working_dir=os.getcwd(),
        max_iterations=50,  # Allow more iterations
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

    # This question should trigger the loop
    prompt = 'ahmet mehmet klasorundeki dosyayi oku'

    print(f"\n[TASK] {prompt}")
    print("\n" + "=" * 80)

    # Run agent
    iteration = 0
    stopped_early = False

    async for response in agent.run(prompt):
        iteration += 1
        print(f"\n[Iteration {iteration}]", end="")

        if response.tool_calls:
            for tc in response.tool_calls:
                print(f" {tc.get('name')}", end="")

        if response.tool_results:
            for tr in response.tool_results:
                if not tr.success:
                    print(" [FAIL]", end="")
                else:
                    print(" [OK]", end="")

        if "Same tool call failed" in response.content:
            print(f"\n\n[SUCCESS] Loop detected and stopped at iteration {iteration}!")
            stopped_early = True
            break

        if response.state.value == "completed":
            print(f"\n\n[OK] Agent completed at iteration {iteration}")
            break

        if iteration > 10:
            print(f"\n\n[WARN] Still running after 10 iterations")

    print("\n" + "=" * 80)
    print("Results")
    print("=" * 80)

    if stopped_early and iteration < 10:
        print(f"[SUCCESS] Loop detection worked! Stopped after {iteration} iterations")
        print("(Previously would have continued for 20+ iterations)")
    elif iteration <= 5:
        print(f"[SUCCESS] Task completed efficiently in {iteration} iterations")
    else:
        print(f"[PARTIAL] Completed in {iteration} iterations (could be better)")

    # Cleanup
    test_file.unlink()
    test_folder.rmdir()
    await provider.close()

if __name__ == "__main__":
    asyncio.run(test_loop_detection())
