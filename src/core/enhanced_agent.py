"""
Enhanced Agent - Claude CLI'dan Üstün
=====================================

Bu modül, tüm gelişmiş özellikleri birleştiren enhanced agent'ı içerir.

Özellikler:
1. Plan-then-execute yaklaşımı
2. Paralel tool execution
3. Self-reflection ve auto-fix
4. Codebase awareness
5. Persistent memory
6. Smart rollback
7. Multi-model orchestration

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional
from uuid import uuid4

from .agent import Agent, AgentConfig, AgentState, AgentResponse
from .tools import ToolRegistry, ToolResult, create_default_tools
from .context import ContextManager, Message, MessageRole
from .providers import ModelProvider, create_provider
from .advanced import (
    Planner,
    ExecutionPlan,
    PlanStep,
    PlanStatus,
    ParallelExecutor,
    SelfReflector,
    ReflectionResult,
    CodebaseIndexer,
    CodebaseIndex,
    PersistentMemory,
    RollbackManager,
)


class ExecutionMode(Enum):
    """Agent execution modu"""
    AUTONOMOUS = "autonomous"      # Tam otomatik
    SUPERVISED = "supervised"      # Her adımda onay
    PLAN_FIRST = "plan_first"     # Önce plan göster, sonra execute
    INTERACTIVE = "interactive"    # Her adımda user input


@dataclass
class EnhancedConfig(AgentConfig):
    """
    Enhanced agent konfigürasyonu
    """
    # Execution
    execution_mode: ExecutionMode = ExecutionMode.PLAN_FIRST
    max_parallel_tools: int = 5
    enable_parallel: bool = True
    
    # Reflection
    enable_reflection: bool = True
    reflection_threshold: float = 0.7  # Bu confidence altında retry
    max_retries: int = 3
    
    # Codebase
    enable_codebase_indexing: bool = True
    index_on_startup: bool = True
    
    # Memory
    enable_memory: bool = True
    memory_db_path: str = "~/.local-agent/memory.db"
    
    # Rollback
    enable_rollback: bool = True
    auto_snapshot: bool = True
    
    # Multi-model
    planner_model: Optional[str] = None  # Farklı model for planning
    reflector_model: Optional[str] = None  # Farklı model for reflection


class EnhancedAgent:
    """
    Enhanced Agent - Claude CLI'dan üstün
    
    Bu agent, Claude CLI'ın tüm özelliklerini içerir ve üzerine:
    - Proactive planning
    - Parallel execution
    - Self-reflection
    - Codebase awareness
    - Persistent memory
    - Smart rollback
    
    ekler.
    """
    
    def __init__(
        self,
        config: EnhancedConfig,
        provider: ModelProvider,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.config = config
        self.provider = provider
        self.tools = tool_registry or create_default_tools(config.working_dir)
        
        # Core components
        self.context = ContextManager(
            max_tokens=config.max_context_tokens,
            reserve_tokens=config.context_reserve_tokens,
        )
        
        # Enhanced components
        self.planner = Planner(
            self._get_planner_provider()
        )
        
        self.executor = ParallelExecutor(
            self.tools,
            max_parallel=config.max_parallel_tools,
        ) if config.enable_parallel else None
        
        self.reflector = SelfReflector(
            self._get_reflector_provider()
        ) if config.enable_reflection else None
        
        self.memory = PersistentMemory(
            config.memory_db_path
        ) if config.enable_memory else None
        
        self.rollback = RollbackManager(
            config.working_dir
        ) if config.enable_rollback else None
        
        # Codebase index (lazy loaded)
        self._codebase_index: Optional[CodebaseIndex] = None
        
        # State
        self.state = AgentState.IDLE
        self.current_plan: Optional[ExecutionPlan] = None
        self.actions_taken: list[dict] = []
        
        # Callbacks
        self._on_plan_created: Optional[Callable[[ExecutionPlan], None]] = None
        self._on_step_complete: Optional[Callable[[PlanStep], None]] = None
        self._on_reflection: Optional[Callable[[ReflectionResult], None]] = None
    
    def _get_planner_provider(self) -> ModelProvider:
        """Planner için provider al"""
        if self.config.planner_model:
            return create_provider("ollama", model=self.config.planner_model)
        return self.provider
    
    def _get_reflector_provider(self) -> ModelProvider:
        """Reflector için provider al"""
        if self.config.reflector_model:
            return create_provider("ollama", model=self.config.reflector_model)
        return self.provider
    
    async def get_codebase_index(self) -> CodebaseIndex:
        """Codebase index al (lazy load)"""
        if self._codebase_index is None and self.config.enable_codebase_indexing:
            indexer = CodebaseIndexer(self.config.working_dir)
            self._codebase_index = await indexer.index()
        return self._codebase_index
    
    def set_callbacks(
        self,
        on_plan_created: Optional[Callable[[ExecutionPlan], None]] = None,
        on_step_complete: Optional[Callable[[PlanStep], None]] = None,
        on_reflection: Optional[Callable[[ReflectionResult], None]] = None,
    ):
        """Callback'leri ayarla"""
        self._on_plan_created = on_plan_created
        self._on_step_complete = on_step_complete
        self._on_reflection = on_reflection
    
    async def run(
        self,
        user_input: str,
        *,
        mode: Optional[ExecutionMode] = None,
    ) -> AsyncGenerator[AgentResponse, None]:
        """
        Enhanced agent çalıştır
        
        Args:
            user_input: Kullanıcı input'u
            mode: Execution mode (override config)
            
        Yields:
            AgentResponse
        """
        execution_mode = mode or self.config.execution_mode
        self.state = AgentState.THINKING
        self.actions_taken = []
        
        start_time = time.time()
        
        # Step 1: Context gathering
        context = await self._gather_context(user_input)
        
        # Step 2: Memory check
        memory_context = ""
        if self.memory:
            memory_context = await self._check_memory(user_input)
        
        full_context = f"{context}\n\n{memory_context}" if memory_context else context
        
        # Step 3: Create plan
        yield AgentResponse(
            id=str(uuid4()),
            content="Creating execution plan...",
            state=AgentState.THINKING,
            iteration=0,
        )
        
        plan = await self.planner.create_plan(
            goal=user_input,
            context=full_context,
            available_tools=self.tools.list_tools(),
        )
        self.current_plan = plan
        
        if self._on_plan_created:
            self._on_plan_created(plan)
        
        # Plan response
        yield AgentResponse(
            id=str(uuid4()),
            content=f"Plan created with {len(plan.steps)} steps:\n\n{plan.to_markdown()}",
            state=AgentState.THINKING,
            iteration=0,
        )
        
        # Step 4: Execute based on mode
        if execution_mode == ExecutionMode.PLAN_FIRST:
            # Kullanıcı onayı bekle (CLI'da handle edilecek)
            yield AgentResponse(
                id=str(uuid4()),
                content="Plan ready. Waiting for approval to execute...",
                state=AgentState.WAITING_USER,
                iteration=0,
            )
            # Burada CLI'dan onay gelecek, sonra continue_execution çağrılacak
            return
        
        # Execute plan
        async for response in self._execute_plan(plan):
            yield response
        
        # Step 5: Reflection
        if self.reflector:
            reflection = await self._reflect()
            
            if self._on_reflection:
                self._on_reflection(reflection)
            
            if not reflection.is_correct and reflection.should_retry:
                retry_count = 0
                while retry_count < self.config.max_retries and reflection.should_retry:
                    yield AgentResponse(
                        id=str(uuid4()),
                        content=f"Issues found: {reflection.issues}. Retrying ({retry_count + 1}/{self.config.max_retries})...",
                        state=AgentState.THINKING,
                        iteration=0,
                    )
                    
                    # Auto-fix attempt
                    async for response in self._attempt_fix(reflection):
                        yield response
                    
                    # Re-reflect
                    reflection = await self._reflect()
                    retry_count += 1
        
        # Step 6: Memory update
        if self.memory:
            await self._update_memory(user_input, plan)
        
        # Final response
        duration_ms = int((time.time() - start_time) * 1000)
        completed, total = plan.get_progress()
        
        self.state = AgentState.COMPLETED
        
        yield AgentResponse(
            id=str(uuid4()),
            content=f"Completed {completed}/{total} steps in {duration_ms}ms",
            state=AgentState.COMPLETED,
            duration_ms=duration_ms,
        )
    
    async def continue_execution(self) -> AsyncGenerator[AgentResponse, None]:
        """
        Plan onaylandıktan sonra execution'a devam et
        """
        if self.current_plan is None:
            yield AgentResponse(
                id=str(uuid4()),
                content="No plan to execute",
                state=AgentState.ERROR,
            )
            return
        
        async for response in self._execute_plan(self.current_plan):
            yield response
    
    async def _gather_context(self, user_input: str) -> str:
        """
        Context topla - codebase awareness
        """
        context_parts = []
        
        # Working directory info
        context_parts.append(f"Working directory: {self.config.working_dir}")
        
        # Codebase summary
        if self.config.enable_codebase_indexing:
            try:
                index = await self.get_codebase_index()
                if index:
                    context_parts.append(f"\nProject summary:\n{index.get_project_summary()}")
                    
                    # Find relevant files based on user input
                    keywords = user_input.lower().split()
                    relevant_files = []
                    
                    for keyword in keywords:
                        for symbol, files in index.symbol_index.items():
                            if keyword in symbol.lower():
                                relevant_files.extend(files)
                    
                    if relevant_files:
                        unique_files = list(set(relevant_files))[:10]
                        context_parts.append(f"\nPotentially relevant files: {', '.join(unique_files)}")
            except:
                pass
        
        return "\n".join(context_parts)
    
    async def _check_memory(self, user_input: str) -> str:
        """Memory'den ilgili bilgileri al"""
        if not self.memory:
            return ""
        
        parts = []
        
        # Project info
        project_info = self.memory.recall_project(self.config.working_dir)
        if project_info:
            parts.append(f"Known project: {project_info.get('name', 'Unknown')} ({project_info.get('language', 'Unknown')})")
        
        # Similar commands
        similar = self.memory.get_similar_commands(user_input, limit=3)
        if similar:
            parts.append("Previously successful commands in similar context:")
            for cmd in similar:
                parts.append(f"  - {cmd['command']}")
        
        # User preferences
        prefs = self.memory.recall_category("user_preferences")
        if prefs:
            parts.append(f"User preferences: {prefs}")
        
        return "\n".join(parts)
    
    async def _execute_plan(
        self,
        plan: ExecutionPlan,
    ) -> AsyncGenerator[AgentResponse, None]:
        """Plan'ı execute et"""
        
        # Take snapshots before execution
        if self.rollback and self.config.auto_snapshot:
            for step in plan.steps:
                if step.tool in ("str_replace", "create_file"):
                    path = step.arguments.get("path", "")
                    if path:
                        self.rollback.take_snapshot(path)
        
        # Execute
        if self.executor and self.config.enable_parallel:
            # Parallel execution
            def on_step_complete(step: PlanStep):
                self.actions_taken.append({
                    "tool": step.tool,
                    "args": step.arguments,
                    "result": step.result or step.error,
                    "success": step.status == PlanStatus.COMPLETED,
                })
                if self._on_step_complete:
                    self._on_step_complete(step)
            
            await self.executor.execute_plan(plan, on_step_complete)
            
            yield AgentResponse(
                id=str(uuid4()),
                content=f"Executed plan:\n\n{plan.to_markdown()}",
                state=AgentState.TOOL_EXECUTING,
            )
        else:
            # Sequential execution
            for step in plan.steps:
                step.status = PlanStatus.IN_PROGRESS
                
                yield AgentResponse(
                    id=str(uuid4()),
                    content=f"Executing: {step.description}",
                    state=AgentState.TOOL_EXECUTING,
                )
                
                tool = self.tools.get_tool(step.tool)
                if tool is None:
                    step.status = PlanStatus.FAILED
                    step.error = f"Unknown tool: {step.tool}"
                    continue
                
                try:
                    result = await tool.execute(**step.arguments)
                    step.status = PlanStatus.COMPLETED if result.success else PlanStatus.FAILED
                    step.result = result.output
                    step.error = result.error
                except Exception as e:
                    step.status = PlanStatus.FAILED
                    step.error = str(e)
                
                self.actions_taken.append({
                    "tool": step.tool,
                    "args": step.arguments,
                    "result": step.result or step.error,
                    "success": step.status == PlanStatus.COMPLETED,
                })
                
                if self._on_step_complete:
                    self._on_step_complete(step)
    
    async def _reflect(self) -> ReflectionResult:
        """Self-reflection yap"""
        if not self.reflector or not self.actions_taken:
            return ReflectionResult(
                is_correct=True,
                confidence=1.0,
                issues=[],
                suggestions=[],
                should_retry=False,
            )
        
        # Son output'u al
        last_output = ""
        for action in reversed(self.actions_taken):
            if action["success"]:
                last_output = action["result"]
                break
        
        return await self.reflector.reflect(
            goal=self.current_plan.goal if self.current_plan else "",
            actions_taken=self.actions_taken,
            final_output=last_output,
        )
    
    async def _attempt_fix(
        self,
        reflection: ReflectionResult,
    ) -> AsyncGenerator[AgentResponse, None]:
        """Reflection'a göre fix attempt"""
        if not reflection.issues:
            return
        
        # Basit retry: planı tekrar execute et
        # Production'da daha sophisticated fix logic olmalı
        
        yield AgentResponse(
            id=str(uuid4()),
            content=f"Attempting to fix issues: {reflection.issues}",
            state=AgentState.THINKING,
        )
        
        # Rollback and retry
        if self.rollback and self.current_plan:
            for step in self.current_plan.steps:
                if step.status == PlanStatus.FAILED:
                    path = step.arguments.get("path", "")
                    if path:
                        self.rollback.rollback(path, steps=1)
                    
                    # Retry step
                    step.status = PlanStatus.PENDING
            
            # Re-execute failed steps
            async for response in self._execute_plan(self.current_plan):
                yield response
    
    async def _update_memory(self, user_input: str, plan: ExecutionPlan):
        """Memory'yi güncelle"""
        if not self.memory:
            return
        
        # Record successful commands
        for action in self.actions_taken:
            if action["success"]:
                self.memory.record_command(
                    command=f"{action['tool']}({action['args']})",
                    context=user_input,
                    success=True,
                    output=action["result"][:1000],
                )
        
        # Update project info
        if self.config.enable_codebase_indexing and self._codebase_index:
            self.memory.remember_project(
                path=self.config.working_dir,
                name=self._codebase_index.root_dir.split("/")[-1],
                language=self._detect_primary_language(),
            )
    
    def _detect_primary_language(self) -> str:
        """Primary language detect et"""
        if not self._codebase_index:
            return "unknown"
        
        language_counts = {}
        for file_info in self._codebase_index.files.values():
            lang = file_info.language
            language_counts[lang] = language_counts.get(lang, 0) + 1
        
        if not language_counts:
            return "unknown"
        
        return max(language_counts.items(), key=lambda x: x[1])[0]
    
    async def rollback_changes(self, steps: int = 1) -> dict[str, bool]:
        """Değişiklikleri geri al"""
        if not self.rollback:
            return {}
        
        results = {}
        for file_path in self.rollback.snapshots.keys():
            results[file_path] = self.rollback.rollback(file_path, steps)
        
        return results
    
    def reset(self):
        """Agent'ı sıfırla"""
        self.state = AgentState.IDLE
        self.current_plan = None
        self.actions_taken = []
        self.context.clear()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_enhanced_agent(
    working_dir: str = ".",
    model: str = "qwen2.5-coder:32b",
    provider_type: str = "ollama",
    **kwargs,
) -> EnhancedAgent:
    """
    Enhanced agent oluştur
    
    Args:
        working_dir: Çalışma dizini
        model: Model ismi
        provider_type: Provider tipi
        **kwargs: Ek config parametreleri
        
    Returns:
        EnhancedAgent
    """
    config = EnhancedConfig(
        working_dir=working_dir,
        model_name=model,
        **kwargs,
    )
    
    provider = create_provider(provider_type, model=model)
    tools = create_default_tools(working_dir)
    
    return EnhancedAgent(config, provider, tools)
