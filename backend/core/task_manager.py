"""
VibeSecurity Task Manager
==========================
Lightweight in-memory background task execution using ThreadPoolExecutor.
Replaces Celery + Redis with zero external dependencies.

Usage:
    task_mgr = TaskManager(max_workers=4)
    task_id = task_mgr.submit(my_function, arg1, arg2)
    status  = task_mgr.get_status(task_id)
"""

import logging
import sys
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from threading import Lock, Semaphore
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


@dataclass
class TaskRecord:
    task_id: str
    state: TaskState = TaskState.PENDING
    result: Any = None
    error: Optional[str] = None
    tool_name: str = ""
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class TaskManager:
    """
    Thread-safe in-memory task manager.
    Submits callables to a ThreadPoolExecutor and tracks their state.
    """

    MAX_CONCURRENT = 8  # Max tasks that may run simultaneously

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="vibesec")
        self._tasks: Dict[str, TaskRecord] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = Lock()
        self._semaphore = Semaphore(self.MAX_CONCURRENT)
        logger.info(f"[TaskManager] Initialized with {max_workers} workers, max_concurrent={self.MAX_CONCURRENT}")

    def _prune_old_tasks(self):
        """Prune tasks older than 1 hour to prevent memory leaks."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=1)
        with self._lock:
            to_delete = []
            for t_id, record in self._tasks.items():
                if record.completed_at and record.completed_at < cutoff:
                    to_delete.append(t_id)
            for t_id in to_delete:
                del self._tasks[t_id]
                if t_id in self._futures:
                    del self._futures[t_id]

    def submit(self, fn: Callable, *args, tool_name: str = "", **kwargs) -> str:
        """
        Submit a callable for background execution.
        Returns a task_id (UUID) for status polling.
        """
        self._prune_old_tasks()

        # Concurrency guard: non-blocking semaphore acquire
        acquired = self._semaphore.acquire(blocking=False)
        if not acquired:
            running_count = sum(1 for t in self._tasks.values() if t.state == TaskState.RUNNING)
            logger.warning(f"[TaskManager] Semaphore full: {running_count} tasks running (max={self.MAX_CONCURRENT})")
            raise RuntimeError(f"Task queue at capacity ({self.MAX_CONCURRENT} concurrent tasks). Try again later.")

        with self._lock:
            # Check queue depth based on pending tasks
            pending_count = sum(1 for t in self._tasks.values() if t.state == TaskState.PENDING)
            if pending_count > self.max_workers * 10:
                logger.warning(f"[TaskManager] High queue depth: {pending_count} pending tasks.")
                if pending_count > self.max_workers * 25:
                    self._semaphore.release()
                    raise RuntimeError("Task queue is full. Try again later.")
        task_id = str(uuid.uuid4())

        with self._lock:
            self._tasks[task_id] = TaskRecord(
                task_id=task_id,
                state=TaskState.PENDING,
                tool_name=tool_name,
            )

        def _wrapper():
            # Mark as RUNNING
            with self._lock:
                self._tasks[task_id].state = TaskState.RUNNING

            try:
                result = fn(*args, **kwargs)

                with self._lock:
                    self._tasks[task_id].state = TaskState.SUCCESS
                    self._tasks[task_id].result = result
                    self._tasks[task_id].completed_at = datetime.now(timezone.utc)

                logger.info(f"[TaskManager] Task {task_id} ({tool_name}) completed successfully")
                return result

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[TaskManager] Task {task_id} ({tool_name}) failed: {e}\n{tb}")

                with self._lock:
                    self._tasks[task_id].state = TaskState.FAILURE
                    # Store a sanitized error to avoid path leakage
                    error_msg = str(e).split('\n')[0][:200]
                    self._tasks[task_id].error = error_msg
                    self._tasks[task_id].completed_at = datetime.now(timezone.utc)

                raise
            finally:
                self._semaphore.release()

        future = self._executor.submit(_wrapper)

        with self._lock:
            self._futures[task_id] = future

        logger.info(f"[TaskManager] Submitted task {task_id} ({tool_name})")
        return task_id

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the current status of a task.
        Returns a dict compatible with the existing /status/{task_id} API.
        """
        with self._lock:
            record = self._tasks.get(task_id)

        if not record:
            return {
                "task_id": task_id,
                "state": "NOT_FOUND",
                "status": "Task not found.",
            }

        base = {
            "task_id": task_id,
            "state": record.state.value,
            "tool": record.tool_name,
        }

        if record.state == TaskState.PENDING:
            base["status"] = "Task is waiting in the queue..."
        elif record.state == TaskState.RUNNING:
            base["status"] = "Task is currently running."
        elif record.state == TaskState.SUCCESS:
            base["result"] = record.result
            base["status"] = "Task completed successfully."
        elif record.state == TaskState.FAILURE:
            base["error"] = record.error
            base["status"] = "Task failed."

        return base

    def shutdown(self, wait: bool = True, cancel_futures: bool = False):
        """Shutdown the thread pool."""
        if sys.version_info >= (3, 9):
            self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        else:
            self._executor.shutdown(wait=wait)
        logger.info("[TaskManager] Shut down.")


# Module-level singleton — created once, shared across the app
task_manager = TaskManager(max_workers=4)
