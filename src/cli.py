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
import sys
from pathlib import Path
from typing import Optional

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
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' not installed. Install with: pip install rich")

from .core.agent import Agent, AgentConfig, AgentState
from .core.tools import create_default_tools, ToolResult
from .core.context import ContextManager
from .core.providers import create_provider
from .core.config import AgentSettings


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
        self._current_spinner = None
        self._tool_count = 0
    
    def _print(self, *args, **kwargs):
        """Print wrapper"""
        if self.console:
            self.console.print(*args, **kwargs)
        else:
            print(*args)
    
    def _on_thinking(self, message: str):
        """Thinking callback - progress göster"""
        pass  # Progress bar ile handle edilecek
    
    def _on_tool_start(self, tool_name: str, args: dict):
        """Tool başladığında"""
        self._tool_count += 1
        
        # Kısa arg summary
        arg_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in list(args.items())[:3])
        if len(args) > 3:
            arg_summary += ", ..."
        
        if self.console:
            self._print(
                f"[dim]┌─ Tool #{self._tool_count}:[/dim] [cyan]{tool_name}[/cyan]"
                f"[dim]({arg_summary})[/dim]"
            )
        else:
            print(f">>> Tool: {tool_name}({arg_summary})")
    
    def _on_tool_end(self, tool_name: str, result: ToolResult):
        """Tool bittiğinde"""
        if self.console:
            status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
            
            # Kısa output preview
            output_preview = result.output[:100].replace("\n", " ")
            if len(result.output) > 100:
                output_preview += "..."
            
            if result.success:
                self._print(f"[dim]└─ {status} {output_preview}[/dim]")
            else:
                self._print(f"[dim]└─ {status}[/dim] [red]{result.error}[/red]")
        else:
            status = "OK" if result.success else "FAIL"
            print(f"<<< {status}: {result.output[:100] if result.success else result.error}")
    
    def _print_welcome(self):
        """Welcome mesajı"""
        if self.console:
            self._print(Panel.fit(
                f"""[bold cyan]Local Agent CLI[/bold cyan]
                
[dim]Model:[/dim] {self.config.model_name}
[dim]Working Dir:[/dim] {self.config.working_dir}
[dim]Tools:[/dim] {', '.join(self.tools.list_tools())}

Type your request or [bold]/help[/bold] for commands.
Press [bold]Ctrl+C[/bold] to cancel, [bold]Ctrl+D[/bold] to exit.""",
                title="🤖 Agent Ready",
                border_style="cyan"
            ))
        else:
            print(f"""
=== Local Agent CLI ===
Model: {self.config.model_name}
Working Dir: {self.config.working_dir}
Tools: {', '.join(self.tools.list_tools())}

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
        """
        Single prompt execution (non-interactive)
        
        Args:
            prompt: User prompt
            
        Returns:
            Final response content
        """
        self._tool_count = 0
        final_content = ""
        
        if self.console:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
                transient=True,
            ) as progress:
                task = progress.add_task("Thinking...", total=None)
                
                async for response in self.agent.run(prompt):
                    if response.tool_calls:
                        progress.update(task, description=f"Running tools... (iteration {response.iteration})")
                    else:
                        progress.update(task, description="Generating response...")
                    
                    if response.state == AgentState.COMPLETED:
                        final_content = response.content
        else:
            print("Processing...")
            async for response in self.agent.run(prompt):
                if response.state == AgentState.COMPLETED:
                    final_content = response.content
        
        self._print_response(final_content)
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
                
                # Agent çalıştır
                self._tool_count = 0
                
                self._print_info(f"Working... (max {self.config.max_iterations} iterations)")
                
                async for response in self.agent.run(prompt):
                    # Progress update
                    if response.tool_calls:
                        self._print_info(f"Iteration {response.iteration}: {len(response.tool_calls)} tool call(s)")
                    
                    # Final response
                    if response.state == AgentState.COMPLETED:
                        self._print_response(response.content)
                        self._print_info(
                            f"Completed in {response.iteration} iteration(s), "
                            f"{response.tokens_used:,} tokens, "
                            f"{response.duration_ms}ms"
                        )
                    
                    # Error
                    elif response.state == AgentState.ERROR:
                        self._print_error(response.content)
                
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


def main():
    """
    CLI entry point
    """
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
    
    args = parser.parse_args()
    
    # Config oluştur
    config = AgentConfig(
        model_name=args.model,
        working_dir=os.path.abspath(args.dir),
        max_iterations=args.max_iterations,
        max_tokens=args.max_tokens,
    )
    
    # CLI oluştur
    cli = CLI(
        config=config,
        provider_type=args.provider,
        model=args.model,
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
