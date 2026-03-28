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
        """
        Model'den yanıt al - provider abstraction

        Bu method, context'i model'e gönderir ve yanıtı parse eder.
        """
        # System prompt'u hazırla ve cache'le
        system_prompt = self._build_system_prompt()

        # Cache system prompt ve tool definitions if using CachedContextManager
        if isinstance(self.context, CachedContextManager):
            self.context.set_system_prompt(system_prompt)
            self.context.set_tool_definitions(self.tools.get_tool_definitions())

        # Messages'ı model formatına çevir
        messages = self.context.to_model_format()

        # Tool definitions
        tool_definitions = self.tools.get_tool_definitions()
        
        # Model'i çağır
        if self._on_thinking:
            self._on_thinking("Thinking...")
        
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
- IMMEDIATELY respond with ALL these questions in a single message as a numbered list:

1. Uydu boyutu? (1U / 2U / 3U / 6U / 12U)
2. Misyon adi?
3. Yörünge tipi? (LEO / SSO / MEO / GTO)
4. Yörünge yüksekligi (km)? (varsayilan: 500)
5. Yörünge egimi (derece)? (SSO icin ~97.4)
6. Tasarim ömrü (yil)?
7. Payload tipi? (Camera / SDR / AIS / IoT / Science / Custom)
8. Payload güç tüketimi (W)?
9. Payload kütlesi (g)?
10. Alt sistemler? (EPS, OBC, UHF, S-Band, ADCS, GPS, Propulsion, Thermal)
11. Günes paneli? (Body-mounted / Deployable 2-panel / Deployable 4-panel)
12. Batarya tipi? (Li-ion 18650 / Li-Po / Li-ion Prismatic)
13. Günlük veri üretimi (MB)?

After the user answers ALL 13 questions, run this bash command (replace values with user answers):
```
cd D:/Private/Projeler/Python/MustafaCLI && D:/Private/Projeler/Python/MustafaCLI/venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign; d=CubeSatDesign(mission_name='MISSION', sat_size='1U', orbit_type='LEO', orbit_altitude=500, orbit_inclination=97.4, design_life=2, payload_type='Camera (EO)', payload_power=5.0, payload_mass=200, subsystems=['eps','obc','com_uhf','adcs'], solar_config='Body-mounted', battery_type='Li-ion 18650', data_budget=100); print(d.to_summary())"
```

IMPORTANT for the bash command:
- Use the FULL python path: D:/Private/Projeler/Python/MustafaCLI/venv/Scripts/python.exe
- cd to D:/Private/Projeler/Python/MustafaCLI first
- Replace ALL parameter values with the user's actual answers
- subsystems must be a Python list like ['eps','obc','com_uhf','adcs']
- Map user answers: UHF->com_uhf, S-Band->com_sband, GPS->gps, Propulsion->propulsion, Thermal->thermal

Then show the design summary table and ask if the user wants to change anything or run analysis.
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
        """
        Context'i compact et - uzun konuşmalar için kritik
        
        Bu method, eski mesajları özetler ve context'i küçültür.
        Claude Code'un uzun session'larda çalışabilmesinin sırrı.
        """
        # Basit compaction: Eski mesajları özetle
        old_messages = self.context.get_old_messages(keep_recent=10)
        
        if not old_messages:
            return
        
        # Model'den özet iste
        summary_prompt = "Summarize the following conversation history in a few sentences, keeping important context:\n\n"
        for msg in old_messages:
            summary_prompt += f"{msg.role.value}: {msg.content[:500]}...\n"
        
        summary_response = await self.provider.complete(
            messages=[{"role": "user", "content": summary_prompt}],
            system="You are a helpful assistant that summarizes conversations concisely.",
            max_tokens=500,
        )
        
        summary = summary_response.get("content", "")
        
        # Context'i güncelle
        self.context.compact(
            summary=summary,
            keep_recent=10,
        )
    
    def reset(self) -> None:
        """Agent state'ini sıfırla"""
        self.state = AgentState.IDLE
        self.current_iteration = 0
        self._consecutive_tool_calls = 0
        self.context.clear()
