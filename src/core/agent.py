"""
Local Agent CLI - Claude Code Architecture Implementation
=========================================================

Bu modül, Claude Code'un agentic loop mimarisini açık kaynak modeller için
adapte eden temel agent sistemini içerir.

Mimari Prensipler:
1. Infinite Loop with Exit Conditions - Görev tamamlanana kadar devam et
2. Tool Use → Observe → Think → Repeat - Her adımda düşün
3. Context Window Management - Akıllı truncation ve compaction
4. Error Recovery - Hatalardan öğren ve düzelt

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional
from uuid import uuid4

from .tools import Tool, ToolResult, ToolRegistry
from .context import ContextManager, CachedContextManager, Message, MessageRole
from .providers import ModelProvider


class AgentState(Enum):
    """Agent durumu - state machine için"""
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_EXECUTING = "tool_executing"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentConfig:
    """
    Agent konfigürasyonu - Claude Code'dan esinlenilmiş
    
    Bu config, agent'ın davranışını kontrol eden tüm parametreleri içerir.
    Production'da bunları environment variables veya config file'dan yükle.
    """
    # Model settings
    model_name: str = "qwen3:8b"
    temperature: float = 0.0  # Deterministic outputs for coding
    max_tokens: int = 8192
    
    # Agent loop settings
    max_iterations: int = 100  # Claude Code ~50, biz daha esnek
    max_consecutive_tool_calls: int = 20  # Sonsuz loop koruması
    thinking_budget: int = 10000  # Extended thinking için token budget
    
    # Context management
    max_context_tokens: int = 32000  # Model'e göre ayarla
    context_reserve_tokens: int = 4000  # Response için rezerv
    compaction_threshold: float = 0.8  # %80 dolunca compact et
    
    # Tool settings
    tool_timeout: int = 300  # 5 dakika timeout
    bash_timeout: int = 120  # Bash commands için
    
    # Working directory
    working_dir: str = "."
    
    # Skills directory - Claude Code'un en önemli özelliği
    skills_dir: Optional[str] = None
    
    # Safety
    allow_dangerous_commands: bool = False
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "mkfs", "dd if=/dev/zero", ":(){:|:&};:"
    ])


@dataclass
class AgentResponse:
    """Agent'ın bir iteration'daki yanıtı"""
    id: str
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    thinking: Optional[str] = None  # Extended thinking content
    state: AgentState = AgentState.THINKING
    iteration: int = 0
    tokens_used: int = 0
    duration_ms: int = 0


class Agent:
    """
    Ana Agent sınıfı - Claude Code mimarisinin kalbi
    
    Bu sınıf, agentic loop'u yönetir ve tool'ları koordine eder.
    
    Kullanım:
        agent = Agent(config, provider, tools)
        async for response in agent.run("Build a REST API"):
            print(response.content)
    """
    
    def __init__(
        self,
        config: AgentConfig,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        context_manager: Optional[ContextManager] = None,
    ):
        self.config = config
        self.provider = provider
        self.tools = tool_registry
        self.context = context_manager or CachedContextManager(
            max_tokens=config.max_context_tokens,
            reserve_tokens=config.context_reserve_tokens,
            enable_cache=True,  # Enable caching for 50-70% performance improvement
        )
        
        self.state = AgentState.IDLE
        self.current_iteration = 0
        self._consecutive_tool_calls = 0

        # Loop detection - track recent failed tools
        self._recent_failed_tools: list[tuple[str, dict]] = []  # [(tool_name, args), ...]
        self._max_same_failure = 2  # Stop after same failure repeats this many times

        # Callbacks for UI integration
        self._on_thinking: Optional[Callable[[str], None]] = None
        self._on_tool_start: Optional[Callable[[str, dict], None]] = None
        self._on_tool_end: Optional[Callable[[str, ToolResult], None]] = None
    
    def set_callbacks(
        self,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_tool_start: Optional[Callable[[str, dict], None]] = None,
        on_tool_end: Optional[Callable[[str, ToolResult], None]] = None,
    ) -> None:
        """UI callback'lerini ayarla - streaming için önemli"""
        self._on_thinking = on_thinking
        self._on_tool_start = on_tool_start
        self._on_tool_end = on_tool_end
    
    async def stream_run(self, user_input: str):
        """Streaming version of run — yields content chunks token-by-token.

        Yields dicts:
          {"type": "content", "text": "..."}   — streamed text token
          {"type": "tool_start", "name": "...", "args": {...}}
          {"type": "tool_end", "name": "...", "success": bool, "output": "..."}
          {"type": "done", "content": "...", "iteration": N, "tokens": N}
          {"type": "error", "message": "..."}
        """
        self.state = AgentState.THINKING
        self.current_iteration = 0
        self._consecutive_tool_calls = 0
        self._recent_failed_tools = []

        self.context.add_message(Message(
            role=MessageRole.USER, content=user_input, timestamp=datetime.now(),
        ))

        system_prompt = self._build_system_prompt()
        if isinstance(self.context, CachedContextManager):
            self.context.set_system_prompt(system_prompt)
            self.context.set_tool_definitions(self.tools.get_tool_definitions())

        while self.current_iteration < self.config.max_iterations:
            self.current_iteration += 1

            if self.context.should_compact(self.config.compaction_threshold):
                await self._compact_context()

            messages = self.context.to_model_format()
            tool_defs = self.tools.get_tool_definitions()

            full_content = ""
            tool_calls = []
            usage = {}

            try:
                async for chunk in self.provider.stream_complete(
                    messages=messages, system=system_prompt,
                    tools=tool_defs, temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ):
                    if chunk["type"] == "content":
                        yield chunk
                        full_content += chunk["text"]
                    elif chunk["type"] == "done":
                        full_content = chunk.get("content", full_content)
                        tool_calls = chunk.get("tool_calls", [])
                        usage = chunk.get("usage", {})
            except Exception as e:
                yield {"type": "error", "message": str(e)}
                return

            if tool_calls:
                self._consecutive_tool_calls += 1
                if self._consecutive_tool_calls > self.config.max_consecutive_tool_calls:
                    yield {"type": "done", "content": full_content + "\n[Max tool calls reached]",
                           "iteration": self.current_iteration, "tokens": usage.get("total_tokens", 0)}
                    return

                self.context.add_message(Message(
                    role=MessageRole.ASSISTANT, content=full_content,
                    tool_calls=tool_calls, timestamp=datetime.now(),
                ))

                tool_calls = self._coerce_tool_args_list(tool_calls)
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("arguments", {})
                    yield {"type": "tool_start", "name": name, "args": args}

                    tool = self.tools.get_tool(name)
                    if tool is None:
                        result = ToolResult(success=False, output="", error=f"Unknown tool: {name}")
                    else:
                        try:
                            coerced = self._coerce_tool_args(args)
                            result = await asyncio.wait_for(
                                tool.execute(**coerced), timeout=self.config.tool_timeout)
                        except Exception as e:
                            result = ToolResult(success=False, output="", error=str(e))

                    yield {"type": "tool_end", "name": name, "success": result.success,
                           "output": result.output[:200] if result.success else result.error[:200]}

                    self.context.add_message(Message(
                        role=MessageRole.TOOL,
                        content=result.output if result.success else f"Error: {result.error}",
                        tool_call_id=tc.get("id", ""), tool_name=name,
                        timestamp=datetime.now(),
                    ))
                continue

            # No tool calls = final response
            self._consecutive_tool_calls = 0
            self.context.add_message(Message(
                role=MessageRole.ASSISTANT, content=full_content, timestamp=datetime.now(),
            ))
            yield {"type": "done", "content": full_content,
                   "iteration": self.current_iteration, "tokens": usage.get("total_tokens", 0)}
            return

    def _coerce_tool_args_list(self, tool_calls: list[dict]) -> list[dict]:
        """Coerce args in a list of tool calls."""
        for tc in tool_calls:
            tc["arguments"] = self._coerce_tool_args(tc.get("arguments", {}))
        return tool_calls

    async def run(
        self,
        user_input: str,
        *,
        stream: bool = True,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Ana agent loop - Claude Code'un çekirdeği
        
        Bu method, kullanıcı input'unu alır ve görev tamamlanana kadar
        iteratif olarak düşünür, tool kullanır, gözlemler.
        
        Args:
            user_input: Kullanıcının mesajı
            stream: Streaming mode (her iteration'da yield)
            
        Yields:
            AgentResponse: Her iteration'daki agent yanıtı
        """
        self.state = AgentState.THINKING
        self.current_iteration = 0
        self._consecutive_tool_calls = 0
        self._recent_failed_tools = []  # Reset failed tools for new query

        # Kullanıcı mesajını context'e ekle
        self.context.add_message(Message(
            role=MessageRole.USER,
            content=user_input,
            timestamp=datetime.now(),
        ))
        
        while self.current_iteration < self.config.max_iterations:
            self.current_iteration += 1
            start_time = time.time()
            
            try:
                # Context window check - gerekirse compact et
                if self.context.should_compact(self.config.compaction_threshold):
                    await self._compact_context()
                
                # Model'den yanıt al
                response = await self._get_model_response()
                
                # Tool calls var mı?
                if response.tool_calls:
                    self.state = AgentState.TOOL_EXECUTING
                    self._consecutive_tool_calls += 1
                    
                    # Sonsuz loop koruması
                    if self._consecutive_tool_calls > self.config.max_consecutive_tool_calls:
                        response.content += "\n\n[Agent: Too many consecutive tool calls. Stopping to prevent infinite loop.]"
                        response.state = AgentState.COMPLETED
                        yield response
                        break
                    
                    # Tool'ları çalıştır
                    tool_results = await self._execute_tools(response.tool_calls)
                    response.tool_results = tool_results

                    # Loop detection: Check for repeated failures
                    for tool_call, result in zip(response.tool_calls, tool_results):
                        if not result.success:
                            tool_signature = (tool_call.get("name"), str(tool_call.get("arguments")))
                            self._recent_failed_tools.append(tool_signature)

                            # Keep only last 10 failures
                            if len(self._recent_failed_tools) > 10:
                                self._recent_failed_tools.pop(0)

                            # Count how many times this exact failure occurred
                            failure_count = self._recent_failed_tools.count(tool_signature)

                            if failure_count >= self._max_same_failure:
                                error_msg = f"\n\n[Agent: Same tool call failed {failure_count} times. Stopping to prevent loop.]\n"
                                error_msg += f"Failed tool: {tool_call.get('name')} with args: {tool_call.get('arguments')}\n"
                                error_msg += f"Error: {result.error}\n"
                                error_msg += "Please try a different approach or ask the user for clarification."
                                response.content += error_msg
                                response.state = AgentState.COMPLETED
                                self.context.add_message(Message(
                                    role=MessageRole.SYSTEM,
                                    content=error_msg,
                                    timestamp=datetime.now(),
                                ))
                                yield response
                                return

                    # Assistant mesajını context'e ekle
                    self.context.add_message(Message(
                        role=MessageRole.ASSISTANT,
                        content=response.content,
                        tool_calls=response.tool_calls,
                        timestamp=datetime.now(),
                    ))
                    
                    # Tool sonuçlarını context'e ekle
                    for tool_call, result in zip(response.tool_calls, tool_results):
                        self.context.add_message(Message(
                            role=MessageRole.TOOL,
                            content=result.output if result.success else f"Error: {result.error}",
                            tool_call_id=tool_call.get("id", str(uuid4())),
                            tool_name=tool_call.get("name", "unknown"),
                            timestamp=datetime.now(),
                        ))
                    
                    response.duration_ms = int((time.time() - start_time) * 1000)
                    yield response
                    
                    # Loop devam ediyor
                    continue
                
                # Tool call yok = final response veya user input bekliyor
                self._consecutive_tool_calls = 0
                
                # Response'u context'e ekle
                self.context.add_message(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    timestamp=datetime.now(),
                ))

                response.state = AgentState.COMPLETED
                response.duration_ms = int((time.time() - start_time) * 1000)
                self.state = AgentState.COMPLETED

                # Cache stats removed — was showing fake/estimated values

                yield response
                break
                
            except Exception as e:
                self.state = AgentState.ERROR
                error_response = AgentResponse(
                    id=str(uuid4()),
                    content=f"Error in iteration {self.current_iteration}: {str(e)}",
                    state=AgentState.ERROR,
                    iteration=self.current_iteration,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                yield error_response
                
                # Hata recovery - context'e ekle ve devam et
                self.context.add_message(Message(
                    role=MessageRole.SYSTEM,
                    content=f"An error occurred: {str(e)}. Please try a different approach.",
                    timestamp=datetime.now(),
                ))
                
                # 3 ardışık hata varsa dur
                if self.current_iteration >= 3:
                    last_messages = self.context.get_recent_messages(3)
                    if all(m.role == MessageRole.SYSTEM and "error" in m.content.lower() 
                           for m in last_messages):
                        break
    
    async def _get_model_response(self) -> AgentResponse:
        """Model'den yanıt al — with automatic error-recovery compaction.

        If the model returns a context-too-long error, progressively compact
        (Level 1 → 2 → 3) and retry before surfacing the error.
        """
        system_prompt = self._build_system_prompt()

        if isinstance(self.context, CachedContextManager):
            self.context.set_system_prompt(system_prompt)
            self.context.set_tool_definitions(self.tools.get_tool_definitions())

        messages = self.context.to_model_format()
        tool_definitions = self.tools.get_tool_definitions()

        if self._on_thinking:
            self._on_thinking("Thinking...")

        last_error = None
        for attempt in range(4):
            try:
                response = await self.provider.complete(
                    messages=messages,
                    system=system_prompt,
                    tools=tool_definitions,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                return AgentResponse(
                    id=response.get("id", str(uuid4())),
                    content=response.get("content", ""),
                    tool_calls=response.get("tool_calls", []),
                    thinking=response.get("thinking"),
                    iteration=self.current_iteration,
                    tokens_used=response.get("usage", {}).get("total_tokens", 0),
                )
            except Exception as exc:
                err = str(exc).lower()
                is_ctx_err = any(p in err for p in [
                    "context length", "too long", "token limit", "num_ctx",
                ])
                if not is_ctx_err or attempt >= 3:
                    raise
                last_error = exc
                if attempt == 0:
                    self.context.snip_old_tool_results(keep_recent=5)
                elif attempt == 1:
                    await self.context.summarize_old_messages(self.provider, keep_recent=10)
                else:
                    self.context.emergency_collapse(keep_recent=3)
                messages = self.context.to_model_format()

        raise last_error
    
    async def _execute_tools(self, tool_calls: list[dict]) -> list[ToolResult]:
        """
        Tool'ları çalıştır - paralel veya sıralı
        
        Claude Code'da tool'lar genellikle sıralı çalışır çünkü
        birbirlerine bağımlı olabilirler. Ama bağımsız tool'lar
        paralel çalışabilir.
        """
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("arguments", {})
            
            # Callback
            if self._on_tool_start:
                self._on_tool_start(tool_name, tool_args)
            
            # Tool'u bul ve çalıştır
            tool = self.tools.get_tool(tool_name)
            if tool is None:
                result = ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown tool: {tool_name}",
                )
            else:
                try:
                    # Coerce string args to proper types (models often send "120" instead of 120)
                    tool_args = self._coerce_tool_args(tool_args)
                    result = await asyncio.wait_for(
                        tool.execute(**tool_args),
                        timeout=self.config.tool_timeout,
                    )
                except asyncio.TimeoutError:
                    result = ToolResult(
                        success=False,
                        output="",
                        error=f"Tool execution timed out after {self.config.tool_timeout}s",
                    )
                except Exception as e:
                    result = ToolResult(
                        success=False,
                        output="",
                        error=str(e),
                    )
            
            # Callback
            if self._on_tool_end:
                self._on_tool_end(tool_name, result)
            
            results.append(result)
        
        return results

    # Argument names that should be numeric (not string paths/content)
    _NUMERIC_ARGS = {"timeout", "max_results", "max_lines"}
    _BOOL_ARGS = {"include_docstrings", "allow_dangerous"}
    _INT_LIST_ARGS = {"line_range"}

    @classmethod
    def _coerce_tool_args(cls, args: dict) -> dict:
        """Coerce tool arguments from strings to proper types.

        LLMs often send numeric values as strings (e.g. timeout="120").
        Only coerce known numeric/bool fields to avoid breaking path strings.
        """
        coerced = {}
        for key, value in args.items():
            if key in cls._NUMERIC_ARGS and isinstance(value, str):
                try:
                    coerced[key] = int(value)
                except ValueError:
                    try:
                        coerced[key] = float(value)
                    except ValueError:
                        coerced[key] = value
            elif key in cls._BOOL_ARGS and isinstance(value, str):
                coerced[key] = value.lower() in ("true", "1", "yes")
            elif key in cls._INT_LIST_ARGS and isinstance(value, list):
                coerced[key] = [
                    int(v) if isinstance(v, str) and v.isdigit() else v
                    for v in value
                ]
            else:
                coerced[key] = value
        return coerced

    def _build_system_prompt(self) -> str:
        """
        System prompt oluştur - Claude Code'un sırrı
        
        Bu prompt, agent'ın davranışını belirler. Skills, working directory,
        ve task-specific instructions burada birleştirilir.
        """
        base_prompt = f"""You are Mustafa CLI, an autonomous AI coding agent. You MUST use your tools to accomplish tasks. NEVER ask clarifying questions when you can find the answer yourself using tools.

## GOLDEN RULE: ACT FIRST, ASK LATER
- When the user asks about a project, IMMEDIATELY use `bash` to list files and `view` to read them
- When the user asks for a report, EXPLORE the directory first, then generate the report
- When the user asks to fix something, READ the code first, then fix it
- ONLY ask questions when the information truly cannot be found using tools
- You have full access to the filesystem — USE IT

## Working Directory
Your working directory is: {self.config.working_dir}
ALWAYS start by exploring this directory when asked about a project.

## Tool Usage — Decision Tree

**User asks about a project / "what's here" / report:**
1. `bash` → `ls` to see project structure (works on both Windows and Linux)
2. `view` → Read key files (README, package.json, requirements.txt, etc.)
3. `bash` → `git log --oneline -10` for recent history
4. Synthesize findings into a comprehensive response

**IMPORTANT: Platform & Performance**
- You are running on {os.name}. Commands run through PowerShell on Windows.
- Use `ls` (works everywhere), `cat` for reading, `git` for version control.
- NEVER use `ls -R` or recursive listing — it can produce massive output and hang.
- To explore a project, use `ls` (top-level only), then `view` specific files.
- Keep bash commands fast — avoid commands that scan entire directory trees.

**User asks to edit a file:**
1. `view` → Read current content
2. `str_replace` → Make the change (NEVER use create_file for existing files!)
3. `view` → Verify the change

**User asks to create something new:**
1. `create_file` → Write the new file
2. `bash` → Run/test if applicable

**User asks to run/test/build:**
1. `bash` → Execute the command
2. Analyze output and report results

## Tools

### bash
- Run shell commands, install packages, test code, explore directories
- Use `ls`, `dir`, `tree`, `find`, `git` to understand project structure
- Check output before proceeding

### view
- Read file contents with syntax awareness
- Always view before editing
- Use line ranges for large files

### str_replace
- Edit existing files by replacing exact text
- old_str must match EXACTLY (spaces, quotes, newlines)
- Example:
  ```tool
  {{"name": "str_replace", "arguments": {{"path": "user.py", "old_str": "name = \\"John\\"", "new_str": "name = \\"Jane\\""}}}}
  ```

### create_file
- Create NEW files only (never for editing existing files)

### git
- Read-only git operations: status, diff, log, blame, show

### search
- Semantic code search across codebase

### ast_analysis
- Analyze Python file structure (classes, functions, imports)

### generate_tests
- Auto-generate pytest test templates

## Error Recovery
- If a tool fails, ANALYZE WHY before retrying
- Do NOT repeat the exact same failing command
- If same error happens 2 times, try a DIFFERENT APPROACH
- Windows paths: use forward slashes or quotes

## Response Style
- Be concise but thorough
- After completing a task, summarize what was done
- Do not ask for confirmation unless the action is destructive

## SAT-MAESTRO Plugin (Satellite Engineering)
When the user asks about satellite design, CubeSat, or engineering analysis:

**CubeSat Design — IMPORTANT:**
When the user says "CubeSat tasarla", "uydu tasarimi", or "satellite design":
- Do NOT explain what a CubeSat is
- Do NOT use any tools
- IMMEDIATELY show ALL questions and ask user to answer them ALL IN ONE MESSAGE:

```
CubeSat Tasarim Formu — tüm cevaplari tek mesajda yazin:

1. Uydu boyutu? (1U / 2U / 3U / 6U / 12U)
2. Misyon adi?
3. Yörünge tipi? (LEO / SSO / MEO / GTO)
4. Yörünge yüksekligi km? (varsayilan: 500)
5. Yörünge egimi derece? (SSO icin ~97.4)
6. Tasarim ömrü yil?
7. Payload tipi? (Camera / SDR / AIS / IoT / Science / Custom)
8. Payload güç tüketimi W?
9. Payload kütlesi g?
10. Alt sistemler? (EPS, OBC, UHF, S-Band, ADCS, GPS, Propulsion, Thermal)
11. Günes paneli? (Body-mounted / Deployable 2-panel / Deployable 4-panel)
12. Batarya tipi? (Li-ion 18650 / Li-Po / Li-ion Prismatic)
13. Günlük veri üretimi MB?

Ornek: 3U, TurkSat-1, SSO, 550, 97.6, 3, Camera, 8, 350, EPS+OBC+UHF+ADCS, Deployable 2-panel, Li-ion 18650, 500
```

Tell the user they can answer like the example — comma-separated in one line or numbered.

When user provides ALL answers in a single message, run this bash command:
```
D:/Private/Projeler/Python/MustafaCLI/venv/Scripts/python.exe D:/Private/Projeler/Python/MustafaCLI/src/plugins/sat_maestro/run_wizard.py --name NAME --size 1U --orbit LEO --altitude 500 --inclination 97.4 --life 2 --payload Camera --payload-power 5 --payload-mass 200 --subsystems eps,obc,com_uhf,adcs --solar Body-mounted --battery Li-ion-18650 --data 100
```

CRITICAL RULES for the command:
- Replace ALL flag values with user's actual answers
- For --subsystems: comma-separated, map: UHF->com_uhf, S-Band->com_sband
- For --solar/--battery: replace spaces with hyphens if needed
- Do NOT use cd, do NOT use python -c, use the EXACT command format above
- Show the output table to user and ask if they want changes
"""
        
        # Skills ekle (eğer varsa)
        if self.config.skills_dir:
            skills_prompt = self._load_relevant_skills()
            if skills_prompt:
                base_prompt += f"\n\n## Available Skills\n{skills_prompt}"
        
        return base_prompt
    
    def _load_relevant_skills(self) -> str:
        """
        İlgili skill'leri yükle - lazy loading
        
        Claude Code'da skill'ler task'a göre dinamik olarak yüklenir.
        Bu method, context'e göre relevant skill'leri belirler.
        """
        # Bu basit implementasyon - production'da daha sofistike olmalı
        # (embedding-based retrieval, keyword matching, etc.)
        return ""
    
    async def _compact_context(self) -> None:
        """3-level context compaction (inspired by Claude Code).

        Level 1 (>60%): Snip old tool results
        Level 2 (>80%): Summarize old conversation via model
        Level 3 (>95%): Emergency collapse to last 3 messages
        """
        usage = self.context.usage_ratio
        if usage > 0.95:
            freed = self.context.emergency_collapse(keep_recent=3)
            if self._on_thinking:
                self._on_thinking(f"Context collapsed — freed ~{freed} tokens")
        elif usage > 0.80:
            freed = await self.context.summarize_old_messages(self.provider, keep_recent=10)
            if self._on_thinking:
                self._on_thinking(f"Summarized old messages — freed ~{freed} tokens")
        elif usage > 0.60:
            freed = self.context.snip_old_tool_results(keep_recent=5)
            if self._on_thinking:
                self._on_thinking(f"Snipped tool results — freed ~{freed} tokens")
    
    def reset(self) -> None:
        """Agent state'ini sıfırla"""
        self.state = AgentState.IDLE
        self.current_iteration = 0
        self._consecutive_tool_calls = 0
        self.context.clear()
