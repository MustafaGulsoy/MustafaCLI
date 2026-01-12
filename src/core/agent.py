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
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional
from uuid import uuid4

from .tools import Tool, ToolResult, ToolRegistry
from .context import ContextManager, Message, MessageRole
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
    model_name: str = "qwen2.5-coder:32b"  # veya "deepseek-coder-v2", "codellama"
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
        self.context = context_manager or ContextManager(
            max_tokens=config.max_context_tokens,
            reserve_tokens=config.context_reserve_tokens,
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
        # System prompt'u hazırla
        system_prompt = self._build_system_prompt()
        
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
    
    def _build_system_prompt(self) -> str:
        """
        System prompt oluştur - Claude Code'un sırrı
        
        Bu prompt, agent'ın davranışını belirler. Skills, working directory,
        ve task-specific instructions burada birleştirilir.
        """
        base_prompt = f"""You are an AI coding assistant with access to tools for file operations and command execution.

## Core Principles

1. **Think Step by Step**: Before taking action, analyze what needs to be done
2. **Verify Before Editing**: Always view files before modifying them
3. **Atomic Changes**: Make small, focused changes rather than large rewrites
4. **Test Your Work**: Run commands to verify changes work
5. **Recover from Errors**: If something fails, analyze why and try a different approach

## Tool Selection - Decision Tree

**Question: Does the file exist?**
- NO → Use `create_file`
- YES → Go to next question

**Question: Do you need to edit the file?**
- NO → Use `view` to read it
- YES → Follow these steps:
  1. Use `view` to read current content
  2. Use `str_replace` to make changes
  3. Use `view` again to verify

**NEVER use create_file to edit existing files!**

## Tool Usage Guidelines

### bash
- Use for running commands, installing packages, testing code
- Always check command output before proceeding
- Use appropriate timeouts for long-running commands

### view
- Use to understand project structure and file contents
- Always view a file before editing it
- Use line ranges for large files

### str_replace - MOST IMPORTANT FOR EDITING FILES
- ALWAYS use this for editing existing files (NOT create_file!)
- STEP 1: Use 'view' to read the file first
- STEP 2: Copy the EXACT text to replace (including whitespace!)
- STEP 3: Provide the new text

Example:
  File contains: name = "John"
  To change it:
  ```tool
  {{
    "name": "str_replace",
    "arguments": {{
      "path": "user.py",
      "old_str": "name = \"John\"",
      "new_str": "name = \"Jane\""
    }}
  }}
  ```

CRITICAL: old_str must match EXACTLY (spaces, quotes, newlines)

### create_file
- Use for creating new files
- Provide complete file content
- Use appropriate file extensions

## Working Directory
Your working directory is: {self.config.working_dir}

## Response Guidelines
- Be concise but thorough
- Show your reasoning when making decisions
- After completing a task, summarize what was done
- If you encounter an error, explain what went wrong and try to fix it
- When a task is complete, clearly state that it's done

## CRITICAL: Task Completion Rules
- If asked to EDIT a file, you MUST use str_replace (viewing alone is NOT enough!)
- If asked to CREATE a file, you MUST use create_file
- If asked to RUN a command, you MUST use bash
- DO NOT stop after just viewing/reading - complete the actual task!
- After making changes, VERIFY them by viewing the file again

## ERROR RECOVERY - MOST IMPORTANT!
- If a tool call FAILS, ANALYZE WHY before trying again
- DO NOT repeat the EXACT SAME failing command
- Common issues:
  * Path with spaces: Use 'ahmet mehmet' NOT ahmet_mehmet
  * Windows: Use forward slashes or quotes for paths
  * Missing file: Check with 'view' first
- If same error happens 2 times, TRY A DIFFERENT APPROACH
- If 'view' works but 'bash' fails for same file → JUST USE VIEW!
- When you answer a question, STOP - don't keep calling tools unnecessarily

## Important
- Do not ask for confirmation before taking actions unless the action is destructive
- If you need to make multiple related changes, do them in sequence
- Always verify your changes work before declaring success
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
