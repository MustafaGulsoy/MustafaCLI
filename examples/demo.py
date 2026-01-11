#!/usr/bin/env python3
"""
Local Agent CLI - Quick Test & Demo
====================================

Bu script, agent sisteminin temel fonksiyonlarını test eder.

Kullanım:
    python examples/demo.py
"""

import asyncio
import os
import sys

# Proje root'unu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.tools import create_default_tools, BashTool, ViewTool, StrReplaceTool
from src.core.context import ContextManager, Message, MessageRole
from src.core.skills import create_skill_registry


async def test_tools():
    """Tool'ları test et"""
    print("\n" + "="*60)
    print("🔧 Testing Tools")
    print("="*60)
    
    working_dir = "/tmp/agent-test"
    os.makedirs(working_dir, exist_ok=True)
    
    tools = create_default_tools(working_dir)
    print(f"✓ Created tools: {tools.list_tools()}")
    
    # Test bash
    bash = tools.get_tool("bash")
    result = await bash.execute(command="echo 'Hello from bash!' && pwd")
    print(f"✓ Bash test: {result.output.strip()}")
    assert result.success, "Bash failed"
    
    # Test create_file
    create = tools.get_tool("create_file")
    result = await create.execute(
        path="test.py",
        content='def hello():\n    return "Hello, World!"\n\nprint(hello())'
    )
    print(f"✓ Create file: {result.output}")
    assert result.success, "Create file failed"
    
    # Test view
    view = tools.get_tool("view")
    result = await view.execute(path="test.py")
    print(f"✓ View file:\n{result.output}")
    assert result.success, "View failed"
    
    # Test str_replace
    replace = tools.get_tool("str_replace")
    result = await replace.execute(
        path="test.py",
        old_str='return "Hello, World!"',
        new_str='return "Hello, Agent!"'
    )
    print(f"✓ Str replace: {result.output}")
    assert result.success, "Str replace failed"
    
    # Verify change
    result = await view.execute(path="test.py")
    assert 'Hello, Agent!' in result.output, "Replace didn't work"
    print("✓ Verified change")
    
    # Test bash to run the script
    result = await bash.execute(command="python test.py")
    print(f"✓ Run script: {result.output.strip()}")
    assert "Hello, Agent!" in result.output, "Script output wrong"
    
    print("\n✅ All tool tests passed!")


def test_context():
    """Context manager'ı test et"""
    print("\n" + "="*60)
    print("📝 Testing Context Manager")
    print("="*60)
    
    ctx = ContextManager(max_tokens=1000, reserve_tokens=200)
    
    # Mesaj ekle
    ctx.add_message(Message(
        role=MessageRole.USER,
        content="Hello, can you help me write a Python script?"
    ))
    
    ctx.add_message(Message(
        role=MessageRole.ASSISTANT,
        content="Of course! What kind of script would you like?"
    ))
    
    stats = ctx.get_stats()
    print(f"✓ Added messages: {stats['total_messages']}")
    print(f"✓ Token usage: {stats['total_tokens']} / {stats['max_tokens']}")
    print(f"✓ Usage ratio: {stats['usage_ratio']:.1%}")
    
    # Model format
    model_messages = ctx.to_model_format()
    print(f"✓ Model format: {len(model_messages)} messages")
    
    # Compaction check
    should_compact = ctx.should_compact(threshold=0.5)
    print(f"✓ Should compact (>50%): {should_compact}")
    
    print("\n✅ Context manager tests passed!")


def test_skills():
    """Skills sistemini test et"""
    print("\n" + "="*60)
    print("🎯 Testing Skills System")
    print("="*60)
    
    registry = create_skill_registry()
    
    print(f"✓ Available skills: {registry.list_skills()}")
    
    # Find relevant skills
    skills = registry.find_relevant_skills(
        query="Create a REST API with FastAPI and PostgreSQL"
    )
    print(f"✓ Found relevant skills: {[s.name for s in skills]}")
    
    # Get skill content
    python_skill = registry.get_skill("python")
    assert python_skill is not None, "Python skill not found"
    print(f"✓ Python skill triggers: {python_skill.triggers}")
    
    # Generate prompt
    prompt = registry.get_skill_prompt(skills[:2])
    print(f"✓ Generated prompt length: {len(prompt)} chars")
    
    print("\n✅ Skills system tests passed!")


async def demo_simple_agent():
    """
    Basit agent demo - gerçek model olmadan tool chain test
    
    Bu demo, agentic loop'un nasıl çalıştığını gösterir.
    """
    print("\n" + "="*60)
    print("🤖 Demo: Simple Agent Workflow")
    print("="*60)
    
    working_dir = "/tmp/agent-demo"
    os.makedirs(working_dir, exist_ok=True)
    os.chdir(working_dir)
    
    tools = create_default_tools(working_dir)
    
    print("\n📋 Scenario: Create a simple Python project")
    print("-" * 40)
    
    # Step 1: Create directory structure
    print("\n[Step 1] Creating directory structure...")
    bash = tools.get_tool("bash")
    result = await bash.execute(command="mkdir -p src tests")
    print(f"  → {result.output or 'Created directories'}")
    
    # Step 2: Create main module
    print("\n[Step 2] Creating main module...")
    create = tools.get_tool("create_file")
    result = await create.execute(
        path="src/calculator.py",
        content='''"""Simple calculator module."""

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b

def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
'''
    )
    print(f"  → {result.output}")
    
    # Step 3: Create test file
    print("\n[Step 3] Creating test file...")
    result = await create.execute(
        path="tests/test_calculator.py",
        content='''"""Tests for calculator module."""
import sys
sys.path.insert(0, "src")

from calculator import add, subtract, multiply, divide

def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    print("✓ add tests passed")

def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5
    print("✓ subtract tests passed")

def test_multiply():
    assert multiply(3, 4) == 12
    assert multiply(-2, 3) == -6
    print("✓ multiply tests passed")

def test_divide():
    assert divide(10, 2) == 5
    assert divide(7, 2) == 3.5
    print("✓ divide tests passed")

if __name__ == "__main__":
    test_add()
    test_subtract()
    test_multiply()
    test_divide()
    print("\\n✅ All tests passed!")
'''
    )
    print(f"  → {result.output}")
    
    # Step 4: View project structure
    print("\n[Step 4] Viewing project structure...")
    view = tools.get_tool("view")
    result = await view.execute(path=".")
    print(f"  → Project structure:\n{result.output}")
    
    # Step 5: Run tests
    print("\n[Step 5] Running tests...")
    result = await bash.execute(command="cd /tmp/agent-demo && python tests/test_calculator.py")
    print(f"  → {result.output}")
    
    # Step 6: Make an edit
    print("\n[Step 6] Adding new function with str_replace...")
    replace = tools.get_tool("str_replace")
    result = await replace.execute(
        path="src/calculator.py",
        old_str='def divide(a: float, b: float) -> float:',
        new_str='''def power(a: float, b: float) -> float:
    """Raise a to the power of b."""
    return a ** b

def divide(a: float, b: float) -> float:'''
    )
    print(f"  → {result.output}")
    
    # Step 7: Verify edit
    print("\n[Step 7] Verifying edit...")
    result = await view.execute(path="src/calculator.py", line_range=[1, 30])
    print(f"  → Updated file:\n{result.output}")
    
    print("\n" + "="*60)
    print("✅ Demo completed successfully!")
    print("="*60)
    print("""
This demo showed the typical agentic workflow:
1. Create directory structure (bash)
2. Create files (create_file)
3. View structure and contents (view)
4. Run commands (bash)
5. Make precise edits (str_replace)
6. Verify changes (view)

In a real agent, the model would decide which tools to use
based on the user's request and the current context.
""")


async def main():
    """Run all tests and demos"""
    print("\n" + "="*60)
    print("🚀 Local Agent CLI - Test Suite")
    print("="*60)
    
    try:
        # Tool tests
        await test_tools()
        
        # Context tests
        test_context()
        
        # Skills tests
        test_skills()
        
        # Demo
        await demo_simple_agent()
        
        print("\n" + "="*60)
        print("🎉 All tests and demos completed successfully!")
        print("="*60)
        print("""
Next steps:
1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh
2. Pull a model: ollama pull qwen2.5-coder:32b
3. Run the CLI: python -m src.cli

Or use programmatically:
    from src import Agent, AgentConfig, create_provider, create_default_tools
""")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
