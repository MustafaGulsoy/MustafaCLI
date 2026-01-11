"""
Debug script for tool calling issue
"""
import asyncio
import json
from src.core.providers import OllamaProvider
from src.core.tools import create_default_tools

async def test_tool_calling():
    """Test tool calling with Ollama"""
    print("=" * 80)
    print("Testing Tool Calling")
    print("=" * 80)

    # Create provider
    provider = OllamaProvider(
        model="qwen2.5-coder:7b",
        base_url="http://localhost:11434"
    )

    # Get tool definitions
    tools = create_default_tools(".")
    tool_defs = tools.get_tool_definitions()

    print(f"\n[OK] Created provider with model: {provider.model}")
    print(f"[OK] Loaded {len(tool_defs)} tools")
    print(f"[OK] Supports native tools: {provider.supports_tools}")

    # Test message
    messages = [
        {"role": "user", "content": 'Bir klasör oluştur adı "test_folder" olsun'}
    ]

    print("\n" + "=" * 80)
    print("Sending request to Ollama...")
    print("=" * 80)

    # Make request
    response = await provider.complete(
        messages=messages,
        system="You are a helpful coding assistant. When asked to perform tasks, use the available tools.",
        tools=tool_defs,
        temperature=0.0,
    )

    print("\n" + "=" * 80)
    print("Response received:")
    print("=" * 80)
    print(f"\nContent:\n{response.get('content', '')}\n")
    print(f"Tool calls: {response.get('tool_calls', [])}")
    print(f"Number of tool calls: {len(response.get('tool_calls', []))}")

    if response.get('tool_calls'):
        print("\n[OK] Tool calls were parsed successfully!")
        for i, call in enumerate(response['tool_calls']):
            print(f"\nTool Call {i+1}:")
            print(f"  Name: {call.get('name')}")
            print(f"  Arguments: {json.dumps(call.get('arguments', {}), indent=4)}")
    else:
        print("\n[FAIL] No tool calls found!")
        print("\nLet's test the parsing function directly...")

        # Test parsing using the existing provider instance
        content = response.get('content', '')
        parsed = provider._parse_tool_calls_from_text(content)

        print(f"\nDirect parsing result: {parsed}")
        print(f"Number of parsed calls: {len(parsed)}")

        if parsed:
            print("\n[OK] Parsing works! The issue is elsewhere.")
        else:
            print("\n[FAIL] Parsing failed! Let's debug the content...")
            print(f"\nRaw content to parse:\n{repr(content)}")

    await provider.close()

    print("\n" + "=" * 80)
    print("Test completed")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_tool_calling())
