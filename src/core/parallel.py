"""
Parallel Execution - Concurrent Tool Execution
================================================

Parallel execution of independent tools for improved performance.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Dict
from enum import Enum

from .logging_config import get_logger
from .exceptions import ToolExecutionError

logger = get_logger(__name__)


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ParallelTask:
    """Parallel task definition."""
    id: str
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = None
    dependencies: List[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}
        if self.dependencies is None:
            self.dependencies = []


class ParallelExecutor:
    """
    Execute tasks in parallel with dependency resolution.

    Features:
    - Concurrent execution of independent tasks
    - Dependency resolution (DAG)
    - Error handling and recovery
    - Progress tracking

    Example:
        executor = ParallelExecutor(max_workers=5)

        # Add tasks
        executor.add_task("task1", some_func, args=(1,))
        executor.add_task("task2", some_func, args=(2,))
        executor.add_task("task3", some_func, args=(3,), dependencies=["task1", "task2"])

        # Execute
        results = await executor.execute_all()
    """

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.tasks: Dict[str, ParallelTask] = {}
        self._completed: set[str] = set()
        self._failed: set[str] = set()

    def add_task(
        self,
        task_id: str,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        dependencies: List[str] = None,
    ) -> None:
        """Add a task to the executor."""
        task = ParallelTask(
            id=task_id,
            name=func.__name__,
            func=func,
            args=args,
            kwargs=kwargs or {},
            dependencies=dependencies or [],
        )
        self.tasks[task_id] = task
        logger.debug("parallel_task_added", task_id=task_id, dependencies=dependencies)

    def can_execute(self, task_id: str) -> bool:
        """Check if task dependencies are satisfied."""
        task = self.tasks[task_id]

        # Check if all dependencies completed
        for dep_id in task.dependencies:
            if dep_id not in self._completed:
                return False

        return True

    async def execute_task(self, task: ParallelTask) -> Any:
        """Execute a single task."""
        task.status = TaskStatus.RUNNING
        logger.info("parallel_task_start", task_id=task.id, name=task.name)

        try:
            # Execute function (handle both sync and async)
            if asyncio.iscoroutinefunction(task.func):
                result = await task.func(*task.args, **task.kwargs)
            else:
                result = await asyncio.to_thread(task.func, *task.args, **task.kwargs)

            task.status = TaskStatus.COMPLETED
            task.result = result
            self._completed.add(task.id)

            logger.info("parallel_task_complete", task_id=task.id, name=task.name)
            return result

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            self._failed.add(task.id)

            logger.error(
                "parallel_task_failed",
                task_id=task.id,
                name=task.name,
                error=str(e),
            )
            raise ToolExecutionError(
                message=f"Task {task.id} failed: {str(e)}",
                tool_name=task.name,
            )

    async def execute_all(self, fail_fast: bool = False) -> Dict[str, Any]:
        """
        Execute all tasks respecting dependencies.

        Args:
            fail_fast: If True, stop on first error

        Returns:
            Dict mapping task_id to result
        """
        results = {}
        pending_tasks = set(self.tasks.keys())
        running_tasks: Dict[str, asyncio.Task] = {}

        logger.info("parallel_execution_start", total_tasks=len(self.tasks))

        while pending_tasks or running_tasks:
            # Find tasks ready to execute
            ready_tasks = [
                task_id for task_id in pending_tasks
                if self.can_execute(task_id)
            ]

            # Start new tasks (up to max_workers)
            slots_available = self.max_workers - len(running_tasks)
            tasks_to_start = ready_tasks[:slots_available]

            for task_id in tasks_to_start:
                task = self.tasks[task_id]
                running_tasks[task_id] = asyncio.create_task(
                    self.execute_task(task)
                )
                pending_tasks.remove(task_id)

            # Wait for at least one task to complete
            if running_tasks:
                done, _ = await asyncio.wait(
                    running_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Process completed tasks
                for task_future in done:
                    # Find task_id
                    task_id = None
                    for tid, tfuture in running_tasks.items():
                        if tfuture == task_future:
                            task_id = tid
                            break

                    if task_id:
                        try:
                            result = await task_future
                            results[task_id] = result
                        except Exception as e:
                            if fail_fast:
                                # Cancel remaining tasks
                                for tfuture in running_tasks.values():
                                    tfuture.cancel()
                                raise

                        del running_tasks[task_id]

        logger.info(
            "parallel_execution_complete",
            total=len(self.tasks),
            completed=len(self._completed),
            failed=len(self._failed),
        )

        return results

    def get_status(self) -> Dict[str, TaskStatus]:
        """Get status of all tasks."""
        return {task_id: task.status for task_id, task in self.tasks.items()}

    def reset(self) -> None:
        """Reset executor state."""
        self.tasks.clear()
        self._completed.clear()
        self._failed.clear()


def create_parallel_tool_calls(tool_calls: List[dict]) -> List[List[dict]]:
    """
    Group tool calls into batches for parallel execution.

    Independent tool calls can be executed in parallel,
    while dependent ones must be sequential.

    Args:
        tool_calls: List of tool call dictionaries

    Returns:
        List of batches (each batch can be executed in parallel)

    Example:
        tool_calls = [
            {"name": "view", "arguments": {"path": "file1.txt"}},
            {"name": "view", "arguments": {"path": "file2.txt"}},
            {"name": "str_replace", "arguments": {...}},  # depends on view
        ]

        batches = create_parallel_tool_calls(tool_calls)
        # Returns: [[view, view], [str_replace]]
    """
    # Simple heuristic: file reads can be parallel, writes must be sequential
    read_tools = {"view", "bash"}  # Tools that don't modify state
    write_tools = {"str_replace", "create_file"}  # Tools that modify state

    batches = []
    current_batch = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("name", "")

        if tool_name in read_tools:
            # Read tools can be batched
            current_batch.append(tool_call)
        else:
            # Write tools: flush current batch and add as single item
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([tool_call])

    # Add remaining batch
    if current_batch:
        batches.append(current_batch)

    return batches
