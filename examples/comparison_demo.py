#!/usr/bin/env python3
"""
Claude CLI vs Enhanced Agent - Comparison & Demo
=================================================

Bu dosya, Claude CLI'ın limitasyonlarını ve Enhanced Agent'ın
bunları nasıl aştığını gösterir.

Author: Mustafa (Kardelen Yazılım)
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.tools import create_default_tools
from src.core.advanced import (
    Planner,
    ExecutionPlan,
    ParallelExecutor,
    SelfReflector,
    CodebaseIndexer,
    PersistentMemory,
    RollbackManager,
)


def print_header(title: str):
    """Header yazdır"""
    print("\n" + "="*70)
    print(f"🔥 {title}")
    print("="*70)


def print_comparison(feature: str, claude_cli: str, enhanced: str):
    """Karşılaştırma tablosu"""
    print(f"\n{'Feature':<25} {'Claude CLI':<25} {'Enhanced Agent':<25}")
    print("-" * 75)
    print(f"{feature:<25} {claude_cli:<25} {enhanced:<25}")


# =============================================================================
# COMPARISON 1: Sequential vs Parallel Execution
# =============================================================================

async def demo_parallel_execution():
    """
    Claude CLI: Sıralı execution - her tool call'dan sonra bekle
    Enhanced: Paralel execution - bağımsız tool'ları aynı anda çalıştır
    
    Örnek senaryo: 5 dosya oluştur
    - Claude CLI: 5 x 200ms = 1000ms
    - Enhanced: 200ms (paralel)
    """
    print_header("1. PARALLEL EXECUTION")
    
    print("""
    Senaryo: 5 bağımsız dosya oluştur
    
    Claude CLI Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ create_file_1 → wait → create_file_2 → wait → ... → done   │
    │ Total time: 5 x tool_time = ~1000ms                         │
    └─────────────────────────────────────────────────────────────┘
    
    Enhanced Agent Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ create_file_1 ─┐                                            │
    │ create_file_2 ─┼─→ all complete → done                      │
    │ create_file_3 ─┤   Total time: ~200ms (5x faster!)          │
    │ create_file_4 ─┤                                            │
    │ create_file_5 ─┘                                            │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    working_dir = "/tmp/parallel-test"
    os.makedirs(working_dir, exist_ok=True)
    
    tools = create_default_tools(working_dir)
    executor = ParallelExecutor(tools, max_parallel=5)
    
    # Simulated plan with 5 independent file creations
    from src.core.advanced import PlanStep, ExecutionPlan, PlanStatus
    
    steps = []
    for i in range(5):
        steps.append(PlanStep(
            id=f"step_{i}",
            description=f"Create file_{i}.txt",
            tool="create_file",
            arguments={
                "path": f"file_{i}.txt",
                "content": f"Content for file {i}\n" * 100,
            },
            dependencies=[],  # Bağımsız!
        ))
    
    plan = ExecutionPlan(
        id="parallel_demo",
        goal="Create 5 files",
        steps=steps,
    )
    
    # Sequential execution (Claude CLI style)
    print("\n📊 Sequential Execution (Claude CLI style):")
    start = time.time()
    for step in steps:
        tool = tools.get_tool(step.tool)
        await tool.execute(**step.arguments)
    sequential_time = time.time() - start
    print(f"   Time: {sequential_time*1000:.0f}ms")
    
    # Clean up
    for i in range(5):
        os.remove(f"{working_dir}/file_{i}.txt")
    
    # Parallel execution (Enhanced style)
    print("\n📊 Parallel Execution (Enhanced Agent):")
    start = time.time()
    await executor.execute_plan(plan)
    parallel_time = time.time() - start
    print(f"   Time: {parallel_time*1000:.0f}ms")
    
    speedup = sequential_time / parallel_time if parallel_time > 0 else 0
    print(f"\n✅ Speedup: {speedup:.1f}x faster!")


# =============================================================================
# COMPARISON 2: Reactive vs Proactive Planning
# =============================================================================

async def demo_planning():
    """
    Claude CLI: Reactive - bir adım yap, sonuca bak, sonraki adıma karar ver
    Enhanced: Proactive - önce tam plan yap, optimize et, sonra execute et
    """
    print_header("2. PROACTIVE PLANNING")
    
    print("""
    Senaryo: REST API oluştur
    
    Claude CLI Yaklaşımı (Reactive):
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Create a REST API"                                    │
    │                                                              │
    │ Claude: *thinks* → creates main.py                          │
    │ Claude: *thinks* → oh, I need models too → creates models.py │
    │ Claude: *thinks* → forgot routes → creates routes.py        │
    │ Claude: *thinks* → need requirements → creates requirements │
    │                                                              │
    │ Problem: No overview, backtracking, inefficient              │
    └─────────────────────────────────────────────────────────────┘
    
    Enhanced Agent Yaklaşımı (Proactive):
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Create a REST API"                                    │
    │                                                              │
    │ Agent: Let me create a plan first...                        │
    │                                                              │
    │ PLAN:                                                        │
    │ ├── Step 1: Create project structure                        │
    │ ├── Step 2: Create models.py (independent)                  │
    │ ├── Step 3: Create routes.py (depends on models)            │
    │ ├── Step 4: Create main.py (depends on routes)              │
    │ ├── Step 5: Create requirements.txt (independent)           │
    │ └── Step 6: Test the API                                    │
    │                                                              │
    │ Benefits:                                                    │
    │ ✓ User can review/modify plan before execution              │
    │ ✓ Parallel execution possible (steps 2 & 5)                 │
    │ ✓ Clear progress tracking                                   │
    │ ✓ Rollback points defined                                   │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    # Demo plan creation
    print("📝 Example plan for 'Create a FastAPI REST API':\n")
    
    example_plan = """
    ⏳ **Step 1**: Create directory structure
       - Tool: `bash`
       - Command: mkdir -p src tests
       
    ⏳ **Step 2**: Create database models (independent)
       - Tool: `create_file`
       - Path: src/models.py
       - Dependencies: []
       
    ⏳ **Step 3**: Create Pydantic schemas (independent)
       - Tool: `create_file`
       - Path: src/schemas.py
       - Dependencies: []
       
    ⏳ **Step 4**: Create CRUD operations
       - Tool: `create_file`
       - Path: src/crud.py
       - Dependencies: [Step 2, Step 3]  # Can't run until models ready
       
    ⏳ **Step 5**: Create API routes
       - Tool: `create_file`
       - Path: src/routes.py
       - Dependencies: [Step 4]
       
    ⏳ **Step 6**: Create main application
       - Tool: `create_file`
       - Path: src/main.py
       - Dependencies: [Step 5]
       
    ⏳ **Step 7**: Create requirements.txt (independent)
       - Tool: `create_file`
       - Dependencies: []
       
    ⏳ **Step 8**: Run tests
       - Tool: `bash`
       - Dependencies: [Step 6, Step 7]
    """
    print(example_plan)
    
    print("""
    🔑 Key Advantages:
    
    1. VISIBILITY: User sees the entire plan before any action
    2. OPTIMIZATION: Steps 2, 3, 7 can run in parallel
    3. ERROR HANDLING: If Step 4 fails, we know exactly what to rollback
    4. PROGRESS: Clear "5/8 steps completed" tracking
    5. MODIFICATION: User can say "skip step 8" or "add step 4.5"
    """)


# =============================================================================
# COMPARISON 3: No Reflection vs Self-Reflection
# =============================================================================

async def demo_self_reflection():
    """
    Claude CLI: Çıktıyı kontrol etmez, hatayı user bulur
    Enhanced: Kendi çıktısını değerlendirir, gerekirse düzeltir
    """
    print_header("3. SELF-REFLECTION")
    
    print("""
    Senaryo: Bir bug fix yap
    
    Claude CLI Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Fix the bug in auth.py"                               │
    │                                                              │
    │ Claude: *reads file* → *makes edit* → "Done!"               │
    │                                                              │
    │ User: *runs tests* → "It's still broken!"                   │
    │                                                              │
    │ Claude: "Oh sorry, let me try again..."                     │
    │                                                              │
    │ Problem: User is the QA engineer                            │
    └─────────────────────────────────────────────────────────────┘
    
    Enhanced Agent Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Fix the bug in auth.py"                               │
    │                                                              │
    │ Agent: *reads file* → *makes edit*                          │
    │                                                              │
    │ Agent (Reflection): Let me verify my work...                │
    │   ├── Run tests: FAILED                                     │
    │   ├── Issues found:                                         │
    │   │   - Missing import statement                            │
    │   │   - Wrong variable name on line 42                      │
    │   └── Confidence: 0.3 (LOW)                                 │
    │                                                              │
    │ Agent: Issues detected. Auto-fixing...                      │
    │   ├── Added missing import                                  │
    │   └── Fixed variable name                                   │
    │                                                              │
    │ Agent (Re-reflection):                                      │
    │   ├── Run tests: PASSED                                     │
    │   └── Confidence: 0.95 (HIGH)                               │
    │                                                              │
    │ Agent: "Fixed! All tests passing."                          │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    # Demo reflection result
    print("📊 Example Reflection Output:\n")
    
    reflection_example = {
        "is_correct": False,
        "confidence": 0.35,
        "issues": [
            "Function 'authenticate' is missing return statement",
            "Variable 'user_id' used before assignment",
            "Exception handling is incomplete",
        ],
        "suggestions": [
            "Add 'return token' at line 45",
            "Initialize user_id at line 30",
            "Wrap database call in try-except",
        ],
        "should_retry": True,
    }
    
    import json
    print(json.dumps(reflection_example, indent=2))
    
    print("""
    
    🔑 Self-Reflection Benefits:
    
    1. QUALITY ASSURANCE: Agent is its own QA
    2. AUTO-FIX: Common issues fixed automatically
    3. CONFIDENCE SCORE: User knows when to double-check
    4. ITERATION: Up to N retries before giving up
    5. LEARNING: Patterns can be stored for future
    """)


# =============================================================================
# COMPARISON 4: Stateless vs Persistent Memory
# =============================================================================

async def demo_persistent_memory():
    """
    Claude CLI: Her session sıfırdan başlar
    Enhanced: Önceki session'lardan öğrenir
    """
    print_header("4. PERSISTENT MEMORY")
    
    print("""
    Senaryo: Aynı projede tekrar çalış
    
    Claude CLI Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ Session 1:                                                   │
    │   User: "This is a Django project with PostgreSQL"          │
    │   Claude: "Got it!" *helps with Django*                     │
    │                                                              │
    │ Session 2 (next day):                                        │
    │   User: "Add a new model"                                   │
    │   Claude: "What framework are you using?"                   │
    │   User: "I told you yesterday, Django!"                     │
    │   Claude: "What database?"                                  │
    │   User: 😤                                                   │
    └─────────────────────────────────────────────────────────────┘
    
    Enhanced Agent Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ Session 1:                                                   │
    │   User: "This is a Django project with PostgreSQL"          │
    │   Agent: "Got it!" *saves to memory*                        │
    │   Memory: {project: Django, db: PostgreSQL, ...}            │
    │                                                              │
    │ Session 2 (next day):                                        │
    │   User: "Add a new model"                                   │
    │   Agent: *checks memory*                                    │
    │   Agent: "I remember this is a Django/PostgreSQL project.   │
    │           Here's your new model with proper field types..." │
    │   User: 😊                                                   │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    # Demo memory
    memory = PersistentMemory("/tmp/demo-memory.db")
    
    # Simulate session 1
    print("📝 Session 1 - Learning:\n")
    memory.remember_fact("project", "framework", "Django")
    memory.remember_fact("project", "database", "PostgreSQL")
    memory.remember_fact("project", "python_version", "3.11")
    memory.remember_fact("user_preferences", "code_style", "black")
    memory.remember_fact("user_preferences", "test_framework", "pytest")
    print("   Remembered: framework=Django, database=PostgreSQL, etc.")
    
    # Simulate session 2
    print("\n📝 Session 2 - Recalling:\n")
    framework = memory.recall_fact("project", "framework")
    database = memory.recall_fact("project", "database")
    prefs = memory.recall_category("user_preferences")
    print(f"   Recalled framework: {framework}")
    print(f"   Recalled database: {database}")
    print(f"   Recalled preferences: {prefs}")
    
    print("""
    
    🔑 Memory Types:
    
    1. FACTS: Key-value pairs about the project
       - Framework, database, language version
       
    2. PATTERNS: Learned coding patterns
       - "User prefers async/await over callbacks"
       
    3. COMMANDS: Successful commands in context
       - "pip install worked for dependencies"
       
    4. PROJECT INFO: Per-project metadata
       - Language, structure, conventions
    """)


# =============================================================================
# COMPARISON 5: No Rollback vs Smart Rollback
# =============================================================================

async def demo_rollback():
    """
    Claude CLI: Hata durumunda manual geri alma gerekir
    Enhanced: Otomatik snapshot ve rollback
    """
    print_header("5. SMART ROLLBACK")
    
    print("""
    Senaryo: Bir edit hatalı oldu
    
    Claude CLI Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Refactor the auth module"                            │
    │                                                              │
    │ Claude: *makes 5 edits across 3 files*                      │
    │ Claude: "Done!"                                             │
    │                                                              │
    │ User: *tests* "It's broken! Revert everything!"            │
    │                                                              │
    │ Claude: "I don't remember the original content..."          │
    │ User: *checks git history* 😰                               │
    │ User: *manually reverts each file*                         │
    └─────────────────────────────────────────────────────────────┘
    
    Enhanced Agent Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Refactor the auth module"                            │
    │                                                              │
    │ Agent: *takes snapshots of all files to be edited*          │
    │ Agent: *makes 5 edits across 3 files*                       │
    │ Agent: "Done! (3 files modified, snapshots saved)"          │
    │                                                              │
    │ User: "It's broken! Revert everything!"                     │
    │                                                              │
    │ Agent: *rollback all changes*                               │
    │ Agent: "Reverted 3 files to their previous state."          │
    │ User: 😊                                                     │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    # Demo rollback
    working_dir = "/tmp/rollback-test"
    os.makedirs(working_dir, exist_ok=True)
    
    # Create initial file
    initial_content = """def authenticate(user, password):
    # Original implementation
    return check_credentials(user, password)
"""
    
    with open(f"{working_dir}/auth.py", "w") as f:
        f.write(initial_content)
    
    rollback = RollbackManager(working_dir)
    
    print("📝 Demo:\n")
    print("1. Original file content:")
    print(f"   {initial_content[:50]}...")
    
    # Take snapshot
    rollback.take_snapshot("auth.py")
    print("\n2. Snapshot taken ✓")
    
    # Make edit
    bad_content = """def authenticate(user, password):
    # Broken implementation
    return None  # Oops!
"""
    with open(f"{working_dir}/auth.py", "w") as f:
        f.write(bad_content)
    print("\n3. Made a bad edit (returns None)")
    
    # Show history
    history = rollback.get_history("auth.py")
    print(f"\n4. File history: {len(history)} snapshots")
    
    # Rollback
    success = rollback.rollback("auth.py", steps=1)
    print(f"\n5. Rollback: {'Success ✓' if success else 'Failed ✗'}")
    
    # Verify
    with open(f"{working_dir}/auth.py", "r") as f:
        restored = f.read()
    print(f"\n6. Restored content:")
    print(f"   {restored[:50]}...")
    
    print("""
    
    🔑 Rollback Features:
    
    1. AUTO-SNAPSHOT: Before every edit
    2. MULTI-LEVEL: Rollback 1, 2, or N steps
    3. PER-FILE: Selective rollback
    4. DIFF VIEW: See what changed
    5. FULL RESET: Rollback all files at once
    """)


# =============================================================================
# COMPARISON 6: No Codebase Awareness vs Full Understanding
# =============================================================================

async def demo_codebase_awareness():
    """
    Claude CLI: Her seferinde dosyaları tek tek okur
    Enhanced: Tüm projeyi indexler ve anlar
    """
    print_header("6. CODEBASE AWARENESS")
    
    print("""
    Senaryo: "Where is the User model defined?"
    
    Claude CLI Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ User: "Where is the User model defined?"                    │
    │                                                              │
    │ Claude: Let me search...                                    │
    │   → grep "class User" . -r                                  │
    │   → cat models/user.py                                      │
    │   → cat models/base.py (maybe here?)                       │
    │   → cat auth/models.py (found it!)                         │
    │                                                              │
    │ Time: ~5 seconds, 4 tool calls                              │
    └─────────────────────────────────────────────────────────────┘
    
    Enhanced Agent Yaklaşımı:
    ┌─────────────────────────────────────────────────────────────┐
    │ *On startup: indexes entire codebase*                       │
    │                                                              │
    │ Index:                                                       │
    │ ├── symbol_index: {                                         │
    │ │     "User": ["auth/models.py"],                           │
    │ │     "Product": ["store/models.py"],                       │
    │ │     ...                                                   │
    │ │   }                                                        │
    │ ├── dependency_graph: {                                     │
    │ │     "auth/views.py": ["auth/models.py", "utils/..."],    │
    │ │   }                                                        │
    │ └── 150 files, 12,000 lines indexed                         │
    │                                                              │
    │ User: "Where is the User model defined?"                    │
    │                                                              │
    │ Agent: *instant lookup*                                     │
    │ Agent: "User is defined in auth/models.py (line 45).       │
    │         It's imported by: auth/views.py, api/serializers.py"│
    │                                                              │
    │ Time: <10ms, 0 tool calls                                   │
    └─────────────────────────────────────────────────────────────┘
    """)
    
    print("""
    🔑 Codebase Index Contents:
    
    1. SYMBOL INDEX
       - All functions, classes, variables
       - Quick lookup: "where is X defined?"
       
    2. DEPENDENCY GRAPH
       - Import/export relationships
       - "What files depend on auth/models.py?"
       
    3. FILE METADATA
       - Language, size, last modified
       - Quick project overview
       
    4. RELATED FILES
       - Given a file, find related files
       - Smart context loading
    """)


# =============================================================================
# SUMMARY
# =============================================================================

def print_summary():
    """Final summary"""
    print_header("SUMMARY: Claude CLI vs Enhanced Agent")
    
    print("""
    ┌─────────────────────────────────────────────────────────────────────┐
    │ Feature              │ Claude CLI      │ Enhanced Agent            │
    ├─────────────────────────────────────────────────────────────────────┤
    │ Execution            │ Sequential      │ Parallel (5x faster)      │
    │ Planning             │ Reactive        │ Proactive (plan first)    │
    │ Quality Assurance    │ User's job      │ Self-reflection           │
    │ Memory               │ Session-only    │ Persistent (cross-session)│
    │ Error Recovery       │ Manual          │ Auto-rollback             │
    │ Codebase Understanding│ File-by-file   │ Full index (instant)      │
    │ Multi-model          │ Single model    │ Specialized models        │
    └─────────────────────────────────────────────────────────────────────┘
    
    💡 Implementation Tips:
    
    1. Start with Planning + Parallel Execution
       - Biggest immediate impact
       - Relatively simple to implement
    
    2. Add Self-Reflection for quality
       - Use same model or cheaper/faster model
       - Run tests as part of reflection
    
    3. Implement Memory for repeat users
       - SQLite is fine for single-user
       - Embedding search for advanced lookup
    
    4. Index codebase for large projects
       - Background indexing
       - Incremental updates on file change
    
    5. Add Rollback for safety
       - Essential for production use
       - Git integration is a bonus
    
    🚀 The goal: Build an agent that's not just as good as Claude CLI,
       but BETTER - faster, smarter, and more reliable.
    """)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    print("\n" + "🔥"*35)
    print("  CLAUDE CLI vs ENHANCED AGENT - Feature Comparison")
    print("🔥"*35)
    
    await demo_parallel_execution()
    await demo_planning()
    await demo_self_reflection()
    await demo_persistent_memory()
    await demo_rollback()
    await demo_codebase_awareness()
    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
