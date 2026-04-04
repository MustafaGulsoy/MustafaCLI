"""
CLI Interface - Rich Terminal UI
================================

Bu modül, terminal üzerinden agent ile etkileşim sağlar.

Özellikler:
- Rich text formatting
- Syntax highlighting
- Streaming output
- Interactive mode
- Progress indicators
- Tool execution visualization

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import asyncio
import argparse
import os
import random
import sys
import time as _time
from pathlib import Path
from typing import Optional

# Force UTF-8 on Windows so Rich spinners render correctly
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Rich imports - güzel terminal output için
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    from rich.prompt import Prompt
    from rich.spinner import Spinner
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' not installed. Install with: pip install rich")

import httpx

# Suppress noisy log output in CLI mode — must run before any logger is created
import logging
from .core.logging_config import setup_logging
setup_logging(log_level="WARNING", log_to_console=False)


# Live status messages
_THINKING_PHRASES = [
    "Thinking",
    "Reasoning",
    "Analyzing",
    "Processing",
    "Vibing",
    "Deep in thought",
    "Connecting the dots",
    "Exploring possibilities",
    "Evaluating",
    "Pondering",
    "Reflecting",
    "Brainstorming",
]

_TOOL_PHRASES = {
    "bash": "Running command",
    "view": "Reading file",
    "str_replace": "Editing file",
    "create_file": "Creating file",
    "git": "Checking git",
    "search": "Searching codebase",
    "ast_analysis": "Analyzing structure",
    "generate_tests": "Generating tests",
}

from .core.agent import Agent, AgentConfig, AgentState
from .core.tools import create_default_tools, ToolResult
from .core.context import ContextManager
from .core.providers import create_provider
from .core.config import AgentSettings


def _get_ollama_models(ollama_url: str = "http://localhost:11434") -> list[dict]:
    """Fetch available models from Ollama."""
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except Exception:
        return []


def _get_mcp_status() -> list[dict]:
    """Detect configured MCP servers from SAT-MAESTRO config."""
    servers = []
    try:
        from .plugins.sat_maestro.config import SatMaestroConfig
        cfg = SatMaestroConfig.from_env()
        servers.append({"name": "neo4j", "endpoint": cfg.neo4j_uri, "type": "database"})
        servers.append({"name": "freecad", "endpoint": cfg.freecad_mcp_command, "type": "cad"})
        servers.append({"name": "gmsh", "endpoint": cfg.gmsh_mcp_command, "type": "mesh"})
        servers.append({"name": "calculix", "endpoint": cfg.calculix_path, "type": "fem"})
    except Exception:
        pass
    return servers


TOOL_CAPABLE_PREFIXES = {"qwen2.5", "qwen2", "qwen3", "llama3.1", "llama3.2", "mistral"}


def _is_tool_capable(model_name: str) -> bool:
    """Check if model supports native tool calling."""
    name_lower = model_name.lower()
    return any(name_lower.startswith(p) for p in TOOL_CAPABLE_PREFIXES)


def _select_model_interactive(console: Console | None, ollama_url: str = "http://localhost:11434") -> str | None:
    """Show interactive model selection menu. Returns chosen model name or None."""
    models = _get_ollama_models(ollama_url)
    if not models:
        if console:
            console.print("[red]Ollama'ya baglanilamadi veya model bulunamadi.[/red]")
            console.print("[dim]Ollama calistigından emin ol: ollama serve[/dim]")
        else:
            print("Ollama'ya baglanilamadi veya model bulunamadi.")
        return None

    if console:
        table = Table(title="Mevcut Modeller", border_style="cyan")
        table.add_column("#", style="bold cyan", width=4)
        table.add_column("Model", style="green")
        table.add_column("Boyut", style="yellow", justify="right")
        table.add_column("Tool", style="dim", justify="center")
        for i, m in enumerate(models, 1):
            size_gb = m.get("size", 0) / (1024 ** 3)
            tool_ok = "[green]OK[/green]" if _is_tool_capable(m["name"]) else "[red]--[/red]"
            table.add_row(str(i), m["name"], f"{size_gb:.1f} GB", tool_ok)
        console.print(table)
        console.print("[dim]Tool=OK modeller agentic calisabilir (tool calling destegi)[/dim]")
        choice = Prompt.ask(
            f"[bold cyan]Model sec (1-{len(models)})[/bold cyan]",
            default="1",
        )
    else:
        print("\nMevcut Modeller:")
        for i, m in enumerate(models, 1):
            size_gb = m.get("size", 0) / (1024 ** 3)
            tool_tag = " [tool]" if _is_tool_capable(m["name"]) else ""
            print(f"  {i}. {m['name']} ({size_gb:.1f} GB){tool_tag}")
        choice = input(f"Model sec (1-{len(models)}) [1]: ") or "1"

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            selected = models[idx]["name"]
            if console and not _is_tool_capable(selected):
                console.print(f"[yellow]Uyari: {selected} tool calling desteklemiyor. Agent mod dusguen calismayabilir.[/yellow]")
            return selected
    except ValueError:
        pass
    return models[0]["name"]


class CLI:
    """
    Command Line Interface for Local Agent
    
    Claude Code benzeri terminal deneyimi.
    """
    
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        provider_type: str = "ollama",
        model: Optional[str] = None,
    ):
        self.console = Console() if RICH_AVAILABLE else None
        self.config = config or AgentConfig()
        
        if model:
            self.config.model_name = model
        
        # Provider oluştur
        self.provider = create_provider(
            provider_type,
            model=self.config.model_name,
        )
        
        # Tools oluştur
        self.tools = create_default_tools(
            working_dir=self.config.working_dir
        )
        
        # Agent oluştur
        self.agent = Agent(
            config=self.config,
            provider=self.provider,
            tool_registry=self.tools,
        )
        
        # Callbacks ayarla
        self.agent.set_callbacks(
            on_thinking=self._on_thinking,
            on_tool_start=self._on_tool_start,
            on_tool_end=self._on_tool_end,
        )
        
        # State
        self._tool_count = 0
        self._live: Live | None = None
        self._phase_start = 0.0

    def _print(self, *args, **kwargs):
        """Print wrapper"""
        if self.console:
            self.console.print(*args, **kwargs)
        else:
            print(*args)

    def _set_status(self, text: str, style: str = "cyan"):
        """Update the live spinner status line."""
        if self._live and self.console:
            elapsed = _time.time() - self._phase_start
            spinner = Spinner("dots", text=f"[{style}]{text}[/{style}] [dim]({elapsed:.0f}s)[/dim]")
            self._live.update(spinner)
        elif not RICH_AVAILABLE:
            print(f"  ... {text}")

    def _on_thinking(self, message: str):
        """Thinking callback"""
        phrase = random.choice(_THINKING_PHRASES)
        self._set_status(phrase)

    def _on_tool_start(self, tool_name: str, args: dict):
        """Tool başladığında"""
        self._tool_count += 1

        # Kısa arg summary
        arg_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in list(args.items())[:2])
        if len(args) > 2:
            arg_summary += ", ..."

        phrase = _TOOL_PHRASES.get(tool_name, f"Running {tool_name}")
        self._set_status(f"{phrase} ({arg_summary})", style="yellow")

        if self.console and self._live:
            # Print tool line above spinner
            self._live.console.print(
                f"  [dim]┌─[/dim] [cyan]{tool_name}[/cyan] [dim]{arg_summary}[/dim]"
            )
        elif not RICH_AVAILABLE:
            print(f">>> Tool: {tool_name}({arg_summary})")

    def _on_tool_end(self, tool_name: str, result: ToolResult):
        """Tool bittiğinde"""
        status_icon = "✓" if result.success else "✗"

        if self.console and self._live:
            if result.success:
                output_preview = result.output[:120].replace("\n", " ")
                if len(result.output) > 120:
                    output_preview += "..."
                self._live.console.print(
                    f"  [dim]└─ [green]{status_icon}[/green] {output_preview}[/dim]"
                )
            else:
                self._live.console.print(
                    f"  [dim]└─ [red]{status_icon}[/red][/dim] [red]{result.error[:120]}[/red]"
                )
            # Back to thinking
            phrase = random.choice(_THINKING_PHRASES)
            self._set_status(phrase)
        elif not RICH_AVAILABLE:
            status = "OK" if result.success else "FAIL"
            print(f"<<< {status}: {result.output[:100] if result.success else result.error}")
    
    def _print_welcome(self):
        """Welcome mesajı"""
        mcp_servers = _get_mcp_status()
        mcp_lines = ""
        if mcp_servers:
            mcp_lines = "\n[dim]MCP Servers:[/dim]"
            for s in mcp_servers:
                mcp_lines += f"\n  [cyan]{s['name']}[/cyan] [dim]({s['type']})[/dim] -> {s['endpoint']}"

        if self.console:
            self._print(Panel.fit(
                f"""[bold cyan]Mustafa CLI[/bold cyan]

[dim]Model:[/dim] [green]{self.config.model_name}[/green]
[dim]Working Dir:[/dim] {self.config.working_dir}
[dim]Tools:[/dim] {', '.join(self.tools.list_tools())}{mcp_lines}

Type your request or [bold]/help[/bold] for commands.
Press [bold]Ctrl+C[/bold] to cancel, [bold]Ctrl+D[/bold] to exit.""",
                title="Mustafa CLI",
                border_style="cyan"
            ))
        else:
            mcp_text = ""
            if mcp_servers:
                mcp_text = "\nMCP Servers:"
                for s in mcp_servers:
                    mcp_text += f"\n  {s['name']} ({s['type']}) -> {s['endpoint']}"
            print(f"""
=== Mustafa CLI ===
Model: {self.config.model_name}
Working Dir: {self.config.working_dir}
Tools: {', '.join(self.tools.list_tools())}{mcp_text}

Type your request or /help for commands.
""")
    
    def _print_response(self, content: str):
        """Agent response'unu formatla"""
        if not content.strip():
            return
        
        if self.console:
            # Markdown rendering
            try:
                md = Markdown(content)
                self._print(Panel(md, title="[bold green]Agent[/bold green]", border_style="green"))
            except Exception:
                self._print(Panel(content, title="[bold green]Agent[/bold green]", border_style="green"))
        else:
            print(f"\n--- Agent ---\n{content}\n")
    
    def _print_error(self, message: str):
        """Error mesajı"""
        if self.console:
            self._print(f"[red]Error:[/red] {message}")
        else:
            print(f"Error: {message}")
    
    def _print_info(self, message: str):
        """Info mesajı"""
        if self.console:
            self._print(f"[dim]{message}[/dim]")
        else:
            print(message)
    
    def _handle_command(self, command: str) -> bool:
        """
        Slash command'ları handle et
        
        Returns:
            bool: True = devam et, False = çık
        """
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd in ("/help", "/h"):
            self._print_help()
        
        elif cmd in ("/quit", "/exit", "/q"):
            return False
        
        elif cmd in ("/clear", "/c"):
            self.agent.reset()
            self._print_info("Context cleared.")
        
        elif cmd == "/stats":
            self._print_stats()
        
        elif cmd == "/model":
            if args:
                self.config.model_name = args[0]
                self._print_info(f"Model changed to: {args[0]}")
            else:
                self._print_info(f"Current model: {self.config.model_name}")
        
        elif cmd == "/tools":
            self._print_tools()
        
        elif cmd == "/cd":
            if args:
                new_dir = os.path.abspath(args[0])
                if os.path.isdir(new_dir):
                    self.config.working_dir = new_dir
                    os.chdir(new_dir)
                    self._print_info(f"Working directory: {new_dir}")
                else:
                    self._print_error(f"Directory not found: {args[0]}")
            else:
                self._print_info(f"Current directory: {self.config.working_dir}")
        
        elif cmd == "/compact":
            self._print_info("Compacting context...")
            # Manual compaction trigger
            asyncio.create_task(self.agent._compact_context())
            self._print_info("Context compacted.")
        
        else:
            self._print_error(f"Unknown command: {cmd}. Type /help for available commands.")
        
        return True
    
    def _print_help(self):
        """Help mesajı"""
        help_text = """
[bold]Available Commands:[/bold]

[cyan]/help, /h[/cyan]      - Show this help message
[cyan]/quit, /exit, /q[/cyan] - Exit the CLI
[cyan]/clear, /c[/cyan]     - Clear conversation context
[cyan]/stats[/cyan]         - Show context statistics
[cyan]/model [name][/cyan]  - Get or set the model
[cyan]/tools[/cyan]         - List available tools
[cyan]/cd [path][/cyan]     - Change working directory
[cyan]/compact[/cyan]       - Manually compact context

[bold]Tips:[/bold]
- Just type your request naturally
- The agent will use tools automatically
- Use Ctrl+C to cancel a running task
- Use Ctrl+D to exit
"""
        if self.console:
            self._print(Panel(help_text, title="Help", border_style="blue"))
        else:
            print(help_text)
    
    def _print_stats(self):
        """Context istatistiklerini göster"""
        stats = self.agent.context.get_stats()
        
        if self.console:
            table = Table(title="Context Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Total Messages", str(stats["total_messages"]))
            table.add_row("Total Tokens", f"{stats['total_tokens']:,}")
            table.add_row("Max Tokens", f"{stats['max_tokens']:,}")
            table.add_row("Available Tokens", f"{stats['available_tokens']:,}")
            table.add_row("Usage", f"{stats['usage_ratio']:.1%}")
            table.add_row("Has Summary", "Yes" if stats["has_compacted_summary"] else "No")
            
            self._print(table)
        else:
            print("\n=== Context Statistics ===")
            for key, value in stats.items():
                print(f"{key}: {value}")
            print()
    
    def _print_tools(self):
        """Tool listesini göster"""
        if self.console:
            table = Table(title="Available Tools")
            table.add_column("Tool", style="cyan")
            table.add_column("Description", style="dim")
            
            for name in self.tools.list_tools():
                tool = self.tools.get_tool(name)
                desc = tool.description.split("\n")[0][:60] + "..."
                table.add_row(name, desc)
            
            self._print(table)
        else:
            print("\n=== Available Tools ===")
            for name in self.tools.list_tools():
                tool = self.tools.get_tool(name)
                print(f"  {name}: {tool.description.split(chr(10))[0]}")
            print()
    
    async def run_single(self, prompt: str) -> str:
        """Single prompt execution with streaming."""
        self._tool_count = 0
        self._phase_start = _time.time()
        final_content = ""
        streaming_text = False

        async for chunk in self.agent.stream_run(prompt):
            ctype = chunk.get("type", "")
            if ctype == "content":
                if not streaming_text:
                    print("Agent: ", end="", flush=True)
                    streaming_text = True
                print(chunk.get("text", ""), end="", flush=True)
            elif ctype == "tool_start":
                if streaming_text:
                    print()
                    streaming_text = False
                name = chunk.get("name", "")
                print(f"  > {name}")
            elif ctype == "tool_end":
                ok = chunk.get("success", False)
                out = chunk.get("output", "")[:100]
                print(f"  {'OK' if ok else 'FAIL'}: {out}")
            elif ctype == "done":
                if streaming_text:
                    print()
                final_content = chunk.get("content", "")
            elif ctype == "error":
                if streaming_text:
                    print()
                print(f"Error: {chunk.get('message', '')}")

        return final_content
    
    async def run_interactive(self):
        """
        Interactive mode - REPL
        
        Claude Code benzeri interaktif deneyim.
        """
        self._print_welcome()
        
        while True:
            try:
                # Prompt
                if self.console:
                    prompt = Prompt.ask("\n[bold cyan]>[/bold cyan]")
                else:
                    prompt = input("\n> ")
                
                # Empty input
                if not prompt.strip():
                    continue
                
                # Command check
                if prompt.startswith("/"):
                    if not self._handle_command(prompt):
                        break
                    continue
                
                # Agent çalıştır (streaming)
                self._tool_count = 0
                self._phase_start = _time.time()
                final_content = ""
                final_iteration = 0
                final_tokens = 0
                had_error = False
                streaming_text = False

                try:
                    async for chunk in self.agent.stream_run(prompt):
                        ctype = chunk.get("type", "")

                        if ctype == "content":
                            if not streaming_text:
                                # First text token — print header
                                if self.console:
                                    self.console.print("\n[green]Agent:[/green] ", end="")
                                else:
                                    print("\nAgent: ", end="")
                                streaming_text = True
                            # Print token immediately
                            text = chunk.get("text", "")
                            if self.console:
                                self.console.print(text, end="", highlight=False)
                            else:
                                print(text, end="", flush=True)

                        elif ctype == "tool_start":
                            if streaming_text:
                                print()  # newline after streamed text
                                streaming_text = False
                            self._tool_count += 1
                            name = chunk.get("name", "")
                            args = chunk.get("args", {})
                            arg_str = ", ".join(f"{k}={repr(v)[:30]}" for k, v in list(args.items())[:2])
                            if self.console:
                                self.console.print(f"  [dim]┌─[/dim] [cyan]{name}[/cyan] [dim]{arg_str}[/dim]")
                            else:
                                print(f"  >>> {name}({arg_str})")

                        elif ctype == "tool_end":
                            name = chunk.get("name", "")
                            ok = chunk.get("success", False)
                            out = chunk.get("output", "")
                            if self.console:
                                icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
                                self.console.print(f"  [dim]└─ {icon} {out[:120]}[/dim]")
                            else:
                                print(f"  <<< {'OK' if ok else 'FAIL'}: {out[:100]}")

                        elif ctype == "done":
                            if streaming_text:
                                print()  # newline
                                streaming_text = False
                            final_content = chunk.get("content", "")
                            final_iteration = chunk.get("iteration", 0)
                            final_tokens = chunk.get("tokens", 0)

                        elif ctype == "error":
                            if streaming_text:
                                print()
                                streaming_text = False
                            self._print_error(chunk.get("message", "Unknown error"))
                            had_error = True

                except KeyboardInterrupt:
                    if streaming_text:
                        print()
                    self._print_info("\nCancelled. Type /quit to exit.")
                    continue

                if not had_error and final_content:
                    elapsed_ms = int((_time.time() - self._phase_start) * 1000)
                    self._print_info(
                        f"Completed in {final_iteration} iteration(s), "
                        f"{final_tokens:,} tokens, "
                        f"{elapsed_ms}ms"
                    )
                
            except KeyboardInterrupt:
                self._print_info("\nCancelled. Type /quit to exit.")
                continue
            
            except EOFError:
                self._print_info("\nGoodbye!")
                break
            
            except Exception as e:
                self._print_error(f"Unexpected error: {e}")
                continue
        
        # Cleanup
        await self.provider.close()


def _handle_plugin_command(argv: list[str]) -> None:
    """Handle `mustafa plugin <subcommand>` commands."""
    from .plugins.manager import install_plugin, remove_plugin, get_installed, get_catalog

    console = Console() if RICH_AVAILABLE else None

    if len(argv) < 1:
        argv = ["list"]

    subcmd = argv[0]

    if subcmd == "list":
        catalog = get_catalog()
        installed = get_installed()
        if console:
            table = Table(title="Plugins", border_style="cyan")
            table.add_column("Plugin", style="green")
            table.add_column("Durum", style="bold", justify="center")
            table.add_column("Aciklama", style="dim")
            for name, info in catalog.items():
                status = "[green]Installed[/green]" if name in installed else "[dim]--[/dim]"
                table.add_row(name, status, info.description)
            console.print(table)
        else:
            for name, info in catalog.items():
                mark = "[installed]" if name in installed else ""
                print(f"  {name} {mark} — {info.description}")

    elif subcmd == "install":
        if len(argv) < 2:
            print("Usage: mustafa plugin install <name>")
            return
        name = argv[1]
        if console:
            console.print(f"[cyan]Installing plugin '{name}'...[/cyan]")

        success, msg = install_plugin(name)
        if success:
            info = get_catalog().get(name)
            if console:
                console.print(f"[green]Plugin '{name}' installed.[/green]")
                if info and info.post_install_notes:
                    console.print("\n[bold]Sonraki adimlar:[/bold]")
                    for note in info.post_install_notes:
                        console.print(f"  [dim]>[/dim] {note}")
                if info and info.docker_compose:
                    console.print(f"\n[yellow]Docker servisleri baslatmak icin:[/yellow]")
                    console.print(f"  docker compose -f {info.docker_compose} up -d")
            else:
                print(f"Plugin '{name}' installed.")
                if info and info.post_install_notes:
                    for note in info.post_install_notes:
                        print(f"  > {note}")
        else:
            if console:
                console.print(f"[red]Install failed:[/red] {msg}")
            else:
                print(f"Install failed: {msg}")

    elif subcmd == "remove":
        if len(argv) < 2:
            print("Usage: mustafa plugin remove <name>")
            return
        name = argv[1]
        success, msg = remove_plugin(name)
        if console:
            if success:
                console.print(f"[green]{msg}[/green]")
            else:
                console.print(f"[red]{msg}[/red]")
        else:
            print(msg)

    else:
        print(f"Unknown plugin command: {subcmd}")
        print("Usage: mustafa plugin [list|install|remove] [name]")


def main():
    """
    CLI entry point
    """
    # Handle `mustafa plugin ...` before argparse
    if len(sys.argv) >= 2 and sys.argv[1] == "plugin":
        _handle_plugin_command(sys.argv[2:])
        return

    # Load settings from .env file
    settings = AgentSettings()

    parser = argparse.ArgumentParser(
        description="Local Agent CLI - Claude Code architecture with open source models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Interactive mode
  %(prog)s "Create a Python script"  # Single prompt
  %(prog)s -m deepseek-coder-v2      # Use specific model
  %(prog)s -p openai -u http://localhost:1234/v1  # Use OpenAI-compatible API
        """
    )
    
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Single prompt to execute (omit for interactive mode)"
    )
    
    parser.add_argument(
        "-m", "--model",
        default=settings.model_name,
        help=f"Model name (default: {settings.model_name})"
    )
    
    parser.add_argument(
        "-p", "--provider",
        choices=["ollama", "openai", "anthropic"],
        default="ollama",
        help="Model provider (default: ollama)"
    )
    
    parser.add_argument(
        "-u", "--url",
        help="Provider base URL (default: provider-specific)"
    )
    
    parser.add_argument(
        "-d", "--dir",
        default=".",
        help="Working directory (default: current)"
    )
    
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum agent iterations (default: 100)"
    )
    
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Maximum tokens per response (default: 8192)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "-s", "--select-model",
        action="store_true",
        help="Interactively select model from Ollama"
    )

    parser.add_argument(
        "--mcp-status",
        action="store_true",
        help="Show MCP server status and exit"
    )

    args = parser.parse_args()

    # MCP status only
    if args.mcp_status:
        console = Console() if RICH_AVAILABLE else None
        servers = _get_mcp_status()
        if not servers:
            print("No MCP servers configured.")
        elif console:
            table = Table(title="MCP Servers", border_style="cyan")
            table.add_column("Server", style="green")
            table.add_column("Type", style="cyan")
            table.add_column("Endpoint", style="dim")
            for s in servers:
                table.add_row(s["name"], s["type"], s["endpoint"])
            console.print(table)
        else:
            for s in servers:
                print(f"  {s['name']} ({s['type']}) -> {s['endpoint']}")
        return

    # Model selection
    model = args.model
    console = Console() if RICH_AVAILABLE else None

    # Interactive model selection: if --select-model or interactive mode without explicit -m
    model_explicitly_set = "-m" in sys.argv or "--model" in sys.argv
    if args.select_model or (not args.prompt and not model_explicitly_set):
        selected = _select_model_interactive(console)
        if selected:
            model = selected
        elif not model_explicitly_set:
            return

    # Config oluştur
    config = AgentConfig(
        model_name=model,
        working_dir=os.path.abspath(args.dir),
        max_iterations=args.max_iterations,
        max_tokens=args.max_tokens,
    )

    # CLI oluştur
    cli = CLI(
        config=config,
        provider_type=args.provider,
        model=model,
    )

    # Çalıştır
    if args.prompt:
        # Single prompt mode
        asyncio.run(cli.run_single(args.prompt))
    else:
        # Interactive mode
        asyncio.run(cli.run_interactive())


if __name__ == "__main__":
    main()
