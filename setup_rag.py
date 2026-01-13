"""
RAG Setup Script
================

Quick setup for RAG (Retrieval Augmented Generation) system.

This script:
1. Checks dependencies
2. Pulls embedding model
3. Indexes codebase
4. Runs test query

Author: Mustafa (Kardelen Yazılım)
"""

import asyncio
import sys
import subprocess
from pathlib import Path


def print_step(step: str, substep: str = ""):
    """Print formatted step"""
    if substep:
        print(f"  └─ {substep}")
    else:
        print(f"\n{'='*60}")
        print(f"  {step}")
        print(f"{'='*60}")


def check_dependencies():
    """Check if required packages are installed"""
    print_step("Step 1: Checking Dependencies")

    required = ["chromadb", "httpx"]
    missing = []

    for pkg in required:
        try:
            __import__(pkg)
            print_step("", f"✓ {pkg} installed")
        except ImportError:
            missing.append(pkg)
            print_step("", f"✗ {pkg} NOT installed")

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("\nInstalling...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", *missing
        ])
        print("\n✓ Dependencies installed!")
    else:
        print("\n✓ All dependencies installed!")


def check_ollama():
    """Check if Ollama is running and has embedding model"""
    print_step("Step 2: Checking Ollama")

    # Check if Ollama is running
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        print_step("", "✓ Ollama is running")
    except:
        print_step("", "✗ Ollama is NOT running")
        print("\nPlease start Ollama first!")
        return False

    # Check if embedding model exists
    try:
        models = response.json().get("models", [])
        model_names = [m["name"] for m in models]

        if any("nomic-embed-text" in name for name in model_names):
            print_step("", "✓ nomic-embed-text model found")
            return True
        else:
            print_step("", "✗ nomic-embed-text model NOT found")
            print("\nPulling model... (this may take a few minutes)")
            subprocess.run(["ollama", "pull", "nomic-embed-text"])
            print("✓ Model pulled!")
            return True
    except Exception as e:
        print(f"Error checking models: {e}")
        return False


async def index_codebase():
    """Index the codebase"""
    print_step("Step 3: Indexing Codebase")

    try:
        from src.rag.indexer import CodebaseIndexer

        indexer = CodebaseIndexer(db_path=".rag_db")
        print_step("", "Scanning files...")

        stats = await indexer.index_codebase(
            root_dir=".",
            force=False  # Incremental
        )

        print_step("", f"✓ Indexed {stats['files_indexed']} files")
        print_step("", f"✓ Created {stats['chunks_created']} chunks")

        # Show DB stats
        db_stats = indexer.get_stats()
        print_step("", f"Total chunks in DB: {db_stats['total_chunks']}")

        return True

    except Exception as e:
        print(f"\nError during indexing: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_retrieval():
    """Test RAG retrieval"""
    print_step("Step 4: Testing Retrieval")

    try:
        from src.rag.retriever import CodeRetriever

        retriever = CodeRetriever(db_path=".rag_db")
        print_step("", "Searching for 'agent execution'...")

        results = await retriever.search("agent execution", n=3)

        if results:
            print_step("", f"✓ Found {len(results)} results")
            for i, r in enumerate(results, 1):
                print(f"\n    {i}. {r.get_location()}")
                print(f"       {r.name} ({r.score:.0%} relevant)")
                print(f"       {r.get_snippet(max_lines=2)[:100]}...")

            return True
        else:
            print_step("", "No results found (this is OK for empty codebase)")
            return True

    except Exception as e:
        print(f"\nError during testing: {e}")
        return False


async def main():
    """Main setup flow"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                    RAG SETUP WIZARD                       ║
║       Retrieval Augmented Generation for MustafaCLI      ║
╚═══════════════════════════════════════════════════════════╝
    """)

    # Step 1: Dependencies
    check_dependencies()

    # Step 2: Ollama
    if not check_ollama():
        print("\n❌ Setup failed: Ollama not ready")
        return False

    # Step 3: Index codebase
    if not await index_codebase():
        print("\n❌ Setup failed: Indexing error")
        return False

    # Step 4: Test
    if not await test_retrieval():
        print("\n❌ Setup failed: Retrieval error")
        return False

    # Success!
    print_step("Setup Complete! 🎉")
    print("""
✓ Dependencies installed
✓ Ollama ready with nomic-embed-text
✓ Codebase indexed
✓ RAG system working

Next Steps:
-----------
1. Use RAG with agent:
   local-agent --enable-rag "explain how agent works"

2. Reindex after code changes:
   python -m src.rag.indexer --path . --force

3. Test search directly:
   python -m src.rag.retriever "your search query"

4. Check RAG guide:
   cat RAG_GUIDE.md

Happy coding! 🚀
    """)

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
