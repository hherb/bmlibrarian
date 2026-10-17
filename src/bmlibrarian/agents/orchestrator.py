"""
Agent orchestration system for managing complex multi-agent workflows.

Provides coordination between agents, handover management, and workflow execution
with progress tracking and error recovery.
"""

from typing import Dict, Any, List, Optional, Callable, Set
import logging
import threading
import time

from .queue_manager import QueueManager, TaskStatus, TaskPriority, QueueTask
from .base import BaseAgent


logger = logging.getLogger(__name__)


class WorkflowStep:
    """Represents a single step in a multi-agent workflow."""
    
    def __init__(self,
                 agent_type: str,
                 method_name: str,
                 priority: TaskPriority = TaskPriority.NORMAL,
                 max_retries: int = 3,
                 depends_on: Optional[List[str]] = None):
        """
        Initialize workflow step.
        
        Args:
            agent_type: Type of agent to execute this step
            method_name: Method to call on the agent
            priority: Task priority
            max_retries: Maximum retry attempts
            depends_on: List of step names this step depends on
        """
        self.agent_type = agent_type
        self.method_name = method_name
        self.priority = priority
        self.max_retries = max_retries
        self.depends_on = depends_on or []


class WorkflowTimeoutError(TimeoutError):
    """Raised when ``execute_workflow`` hits its deadline before finishing.

    The run's still-queued tasks are cancelled. A task an agent has already
    started cannot be stopped: it finishes in the background and its result
    is discarded. Such steps are listed in ``running_steps``.
    """

    def __init__(self, workflow_name: str, unfinished_steps: List[str],
                 results: Dict[str, Any],
                 running_steps: Optional[Dict[str, str]] = None):
        """
        Initialize the error.

        Args:
            workflow_name: Name of the workflow that timed out
            unfinished_steps: Steps not yet completed, failed or skipped
            results: Results of the steps that did complete
            running_steps: Steps whose tasks were already running, mapped
                to their queue task IDs
        """
        super().__init__(
            f"Workflow {workflow_name} timed out with unfinished steps: "
            f"{', '.join(unfinished_steps)}"
        )
        self.workflow_name = workflow_name
        self.unfinished_steps = list(unfinished_steps)
        self.results = dict(results)
        self.running_steps = dict(running_steps or {})


class Workflow:
    """Defines a multi-step workflow with dependencies.

    When a run finishes, each step is in exactly one of three terminal
    states: completed, failed, or skipped (a dependency failed or was
    skipped). Steps handed to the queue but not yet finished are
    *submitted*; they are never handed out again. A run that times out or
    aborts can leave steps unfinished. The ``mark_*`` methods raise on an
    unknown step or one already finished, so a step never holds two states.
    """

    def __init__(self, name: str):
        """
        Initialize an empty workflow.

        Args:
            name: Workflow name (the key used by ``execute_workflow``)
        """
        self.name = name
        self.steps: Dict[str, WorkflowStep] = {}
        self.completed_steps: Set[str] = set()
        self.failed_steps: Set[str] = set()
        self.skipped_steps: Set[str] = set()
        self.submitted_steps: Set[str] = set()

    def add_step(self, name: str, step: WorkflowStep) -> None:
        """Add a step to the workflow."""
        self.steps[name] = step

    def reset(self) -> None:
        """Forget all progress so the workflow can be executed again."""
        self.completed_steps.clear()
        self.failed_steps.clear()
        self.skipped_steps.clear()
        self.submitted_steps.clear()

    def validate(self) -> None:
        """
        Check the dependency graph is well formed: no unknown dependencies
        and no cycles.

        Raises:
            ValueError: A step depends on an unknown step, or the
                dependencies contain a cycle.
        """
        for name, step in self.steps.items():
            unknown = [dep for dep in step.depends_on if dep not in self.steps]
            if unknown:
                raise ValueError(
                    f"Workflow {self.name}: step {name} depends on unknown "
                    f"step(s): {', '.join(unknown)}"
                )

        # Kahn's algorithm: whatever cannot be ordered lies on or behind a cycle.
        remaining = {name: set(step.depends_on) for name, step in self.steps.items()}
        while remaining:
            free = [name for name, deps in remaining.items() if not deps]
            if not free:
                raise ValueError(
                    f"Workflow {self.name}: dependency cycle; steps on or "
                    f"depending on it: {', '.join(sorted(remaining))}"
                )
            for name in free:
                del remaining[name]
            for deps in remaining.values():
                deps.difference_update(free)

    def _is_finished(self, step_name: str) -> bool:
        """Return True if the step has reached a terminal state."""
        return (step_name in self.completed_steps
                or step_name in self.failed_steps
                or step_name in self.skipped_steps)

    def get_ready_steps(self) -> List[str]:
        """Get steps that are ready to execute (dependencies satisfied).

        Steps already submitted or finished are excluded.
        """
        ready = []
        for name, step in self.steps.items():
            if (name not in self.submitted_steps
                    and not self._is_finished(name)
                    and all(dep in self.completed_steps for dep in step.depends_on)):
                ready.append(name)
        return ready

    def get_unfinished_steps(self) -> List[str]:
        """Get steps that are neither completed, failed nor skipped."""
        return [name for name in self.steps if not self._is_finished(name)]

    def _require_unfinished(self, step_name: str) -> None:
        """
        Guard a state change: the step must exist and not be finished.

        Raises:
            KeyError: The workflow has no such step
            ValueError: The step already completed, failed or was skipped
        """
        if step_name not in self.steps:
            raise KeyError(f"Workflow {self.name}: unknown step {step_name}")
        if self._is_finished(step_name):
            raise ValueError(f"Workflow {self.name}: step {step_name} already finished")

    def mark_submitted(self, step_name: str) -> None:
        """
        Mark a step as handed to the queue.

        Raises:
            KeyError: The workflow has no such step
            ValueError: The step is already submitted or finished
        """
        self._require_unfinished(step_name)
        if step_name in self.submitted_steps:
            raise ValueError(f"Workflow {self.name}: step {step_name} already submitted")
        self.submitted_steps.add(step_name)

    def mark_completed(self, step_name: str) -> None:
        """
        Mark a step as completed.

        Raises:
            KeyError: The workflow has no such step
            ValueError: The step already finished
        """
        self._require_unfinished(step_name)
        self.submitted_steps.discard(step_name)
        self.completed_steps.add(step_name)

    def mark_failed(self, step_name: str) -> List[str]:
        """
        Mark a step as failed and skip every step that depends on it.

        Dependents that already finished are left as they are.

        Args:
            step_name: The failed step

        Returns:
            Names of the steps newly skipped because of this failure,
            including indirect dependents.

        Raises:
            KeyError: The workflow has no such step
            ValueError: The step already finished
        """
        self._require_unfinished(step_name)
        self.submitted_steps.discard(step_name)
        self.failed_steps.add(step_name)

        skipped: List[str] = []
        blocked = {step_name}
        changed = True
        while changed:
            changed = False
            for name, step in self.steps.items():
                if self._is_finished(name) or name in self.submitted_steps:
                    continue
                if blocked.intersection(step.depends_on):
                    self.skipped_steps.add(name)
                    blocked.add(name)
                    skipped.append(name)
                    changed = True
        return skipped

    def is_complete(self) -> bool:
        """Check if every step has reached a terminal state."""
        return not self.get_unfinished_steps()


class AgentOrchestrator:
    """
    Orchestrates multi-agent workflows with task queuing and handover management.
    
    Features:
    - Multi-agent workflow coordination
    - Automatic task handovers between agents
    - Progress tracking and callbacks
    - Error recovery and retry logic
    - Concurrent processing support
    - Workflow dependency management
    """
    
    def __init__(self, 
                 queue_manager: Optional[QueueManager] = None,
                 max_workers: int = 4,
                 polling_interval: float = 1.0):
        """
        Initialize orchestrator.
        
        Args:
            queue_manager: Queue manager instance. Creates default if None.
            max_workers: Maximum number of concurrent agent workers
            polling_interval: How often to poll for new tasks (seconds)
        """
        self.queue = queue_manager or QueueManager()
        self.max_workers = max_workers
        self.polling_interval = polling_interval
        
        # Agent registry
        self.agents: Dict[str, BaseAgent] = {}
        
        # Workflow management
        self.active_workflows: Dict[str, Workflow] = {}
        
        # Progress callbacks
        self.progress_callbacks: List[Callable[[str, str, Any], None]] = []
        
        # Control flags
        self._stop_processing = threading.Event()
        self._processing_started = False
        self._processing_threads: List[threading.Thread] = []
        self._agent_threads: Dict[str, threading.Thread] = {}

        # Names of workflows currently inside execute_workflow
        self._running_workflows: Set[str] = set()
        self._workflow_lock = threading.Lock()

    def register_agent(self, agent_type: str, agent: BaseAgent):
        """Register an agent for task processing.

        If processing is already running, a processing thread is started for
        the new agent type straight away.
        """
        self.agents[agent_type] = agent
        logger.info(f"Registered agent: {agent_type}")
        if not self._processing_started:
            return
        if agent_type in self._agent_types_without_workers([agent_type]):
            self._start_agent_thread(agent_type, agent)
        else:
            logger.warning(
                f"Agent {agent_type} re-registered while processing; its running "
                f"thread keeps the previous agent until processing restarts"
            )

    def add_progress_callback(self, callback: Callable[[str, str, Any], None]):
        """Add a progress tracking callback."""
        self.progress_callbacks.append(callback)

    def _notify_progress(self, event_type: str, message: str, data: Any = None):
        """Notify all progress callbacks.

        A failing callback is logged with its traceback and does not stop the
        others or the caller.
        """
        for callback in self.progress_callbacks:
            try:
                callback(event_type, message, data)
            except Exception as e:
                logger.error(f"Progress callback failed on {event_type} event: {e}",
                             exc_info=True)
    
    def submit_task(self,
                   target_agent: str,
                   method_name: str,
                   data: Dict[str, Any],
                   source_agent: Optional[str] = None,
                   priority: TaskPriority = TaskPriority.NORMAL,
                   max_retries: int = 3) -> str:
        """
        Submit a single task for processing.
        
        Returns:
            Task ID
        """
        task_id = self.queue.add_task(
            target_agent=target_agent,
            method_name=method_name,
            data=data,
            source_agent=source_agent,
            priority=priority,
            max_retries=max_retries
        )
        
        self._notify_progress("task_submitted", f"Submitted task {task_id} to {target_agent}", {
            "task_id": task_id,
            "target_agent": target_agent,
            "method_name": method_name
        })
        
        return task_id
    
    def submit_batch_tasks(self,
                          target_agent: str,
                          method_name: str,
                          data_list: List[Dict[str, Any]],
                          source_agent: Optional[str] = None,
                          priority: TaskPriority = TaskPriority.NORMAL,
                          max_retries: int = 3) -> List[str]:
        """
        Submit multiple tasks efficiently.
        
        Returns:
            List of task IDs
        """
        task_ids = self.queue.add_batch_tasks(
            target_agent=target_agent,
            method_name=method_name,
            data_list=data_list,
            source_agent=source_agent,
            priority=priority,
            max_retries=max_retries
        )
        
        self._notify_progress("batch_tasks_submitted", 
                            f"Submitted {len(task_ids)} tasks to {target_agent}", {
            "task_ids": task_ids,
            "target_agent": target_agent,
            "method_name": method_name,
            "count": len(task_ids)
        })
        
        return task_ids
    
    def create_workflow(self, name: str) -> Workflow:
        """Create a new workflow."""
        workflow = Workflow(name)
        self.active_workflows[name] = workflow
        return workflow
    
    def _submit_workflow_step(self, workflow: Workflow, step_name: str,
                              initial_data: Dict[str, Any],
                              results: Dict[str, Any]) -> str:
        """
        Submit one workflow step to the queue.

        The step receives the initial data plus each dependency's result
        under ``<dependency>_result``.

        Returns:
            The queue task ID
        """
        step = workflow.steps[step_name]
        step_data = {**initial_data}
        for dep in step.depends_on:
            if dep in results:
                step_data[f"{dep}_result"] = results[dep]

        task_id = self.submit_task(
            target_agent=step.agent_type,
            method_name=step.method_name,
            data=step_data,
            source_agent="orchestrator",
            priority=step.priority,
            max_retries=step.max_retries
        )
        workflow.mark_submitted(step_name)
        return task_id

    def _fail_workflow_step(self, workflow: Workflow, step_name: str,
                            error: str, status: str) -> None:
        """
        Mark a step failed, skip its dependents and report both.

        Args:
            workflow: The running workflow
            step_name: The failed step
            error: Why the step failed
            status: How its task ended: ``failed``, ``cancelled`` or ``missing``
        """
        logger.error(f"Workflow {workflow.name}: step {step_name} failed: {error}")
        self._notify_progress("workflow_step_failed",
                              f"Step {step_name} failed: {error}", {
            "workflow_name": workflow.name,
            "step_name": step_name,
            "error": error,
            "status": status
        })
        for skipped in workflow.mark_failed(step_name):
            logger.warning(
                f"Workflow {workflow.name}: skipping step {skipped} "
                f"(dependency {step_name} did not complete)"
            )
            self._notify_progress("workflow_step_skipped",
                                  f"Step {skipped} skipped: dependency {step_name} failed", {
                "workflow_name": workflow.name,
                "step_name": skipped,
                "failed_dependency": step_name
            })

    def _poll_workflow_tasks(self, workflow: Workflow, task_step_map: Dict[str, str],
                             results: Dict[str, Any]) -> None:
        """
        Record the outcome of every in-flight task that has finished.

        Finished tasks are removed from ``task_step_map``; completed steps
        add their result to ``results``.
        """
        for task_id, step_name in list(task_step_map.items()):
            task_status = self.queue.get_task_status(task_id)
            if task_status is None:
                del task_step_map[task_id]
                self._fail_workflow_step(
                    workflow, step_name,
                    f"task {task_id} disappeared from the queue "
                    f"(deleted by a queue cleanup?)",
                    status="missing")
            elif task_status.status == TaskStatus.COMPLETED:
                del task_step_map[task_id]
                results[step_name] = task_status.result
                workflow.mark_completed(step_name)
                self._notify_progress("workflow_step_completed",
                                      f"Step {step_name} completed", {
                    "workflow_name": workflow.name,
                    "step_name": step_name,
                    "result": task_status.result
                })
            elif task_status.status == TaskStatus.FAILED:
                del task_step_map[task_id]
                self._fail_workflow_step(workflow, step_name,
                                         task_status.error_message or "task failed",
                                         status="failed")
            elif task_status.status == TaskStatus.CANCELLED:
                del task_step_map[task_id]
                # A retried task keeps its last attempt's error; report the
                # cancellation itself and give that error only as context.
                error = "task cancelled"
                if task_status.error_message:
                    error += f" (last error: {task_status.error_message})"
                self._fail_workflow_step(workflow, step_name, error, status="cancelled")

    def _cancel_pending_tasks(self, workflow: Workflow,
                              task_step_map: Dict[str, str]) -> Dict[str, str]:
        """
        Cancel this run's tasks that no agent has started yet.

        Returns:
            The steps whose tasks could not be cancelled (already running,
            or the cancellation itself failed), mapped to their task IDs
        """
        still_running: Dict[str, str] = {}
        for task_id, step_name in task_step_map.items():
            try:
                cancelled = self.queue.cancel_task(task_id)
            except Exception as e:
                logger.error(f"Workflow {workflow.name}: could not cancel task "
                             f"{task_id} of step {step_name}: {e}", exc_info=True)
                cancelled = False
            if not cancelled:
                still_running[step_name] = task_id
        if still_running:
            logger.warning(
                f"Workflow {workflow.name}: tasks still running after the run "
                f"ended, results will be discarded: {still_running}"
            )
        return still_running

    def execute_workflow(self, workflow_name: str, initial_data: Dict[str, Any],
                         timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute a workflow with dependency management.

        Blocks, polling the queue, until every step has completed, failed or
        been skipped. Agents must be processing the queue (see
        ``start_processing``); with no processing thread for a step's agent
        and no ``timeout``, the call waits indefinitely. Step methods are
        called with the initial data plus each dependency's result under
        ``<dependency>_result`` as keyword arguments. A step whose task
        fails, is cancelled or disappears from the queue counts as failed,
        and every step depending on it (directly or indirectly) is skipped.
        Each execution starts from a clean state, so a workflow can be
        executed repeatedly, but not concurrently with itself.

        Args:
            workflow_name: Name of workflow to execute
            initial_data: Initial data for workflow steps
            timeout: Maximum time to wait in seconds (None waits indefinitely)

        Returns:
            Dictionary of results of the completed steps; failed and skipped
            steps are absent (see the workflow's ``failed_steps`` and
            ``skipped_steps``, and the ``success`` flag of the
            ``workflow_completed`` progress event)

        Raises:
            ValueError: Unknown workflow, a dependency on an unknown step, a
                dependency cycle, or a step for an unregistered agent type
            RuntimeError: The workflow is already being executed
            WorkflowTimeoutError: The timeout passed before the workflow
                finished; the run's queued tasks are cancelled
            Exception: Any error from the queue is re-raised after the
                run's queued tasks are cancelled
        """
        workflow = self.active_workflows.get(workflow_name)
        if not workflow:
            raise ValueError(f"Workflow {workflow_name} not found")

        workflow.validate()
        agent_types = [step.agent_type for step in workflow.steps.values()]
        unregistered = sorted({t for t in agent_types if t not in self.agents})
        if unregistered:
            raise ValueError(
                f"Workflow {workflow_name} uses unregistered agent type(s): "
                f"{', '.join(unregistered)}"
            )
        idle = self._agent_types_without_workers(agent_types)
        if idle:
            logger.warning(
                f"Workflow {workflow_name}: no processing thread for agent "
                f"type(s) {', '.join(idle)}; their steps will not run until "
                f"start_processing() is called"
            )

        with self._workflow_lock:
            if workflow_name in self._running_workflows:
                raise RuntimeError(f"Workflow {workflow_name} is already being executed")
            self._running_workflows.add(workflow_name)
        try:
            return self._run_workflow(workflow, initial_data, timeout)
        finally:
            with self._workflow_lock:
                self._running_workflows.discard(workflow_name)

    def _run_workflow(self, workflow: Workflow, initial_data: Dict[str, Any],
                      timeout: Optional[float]) -> Dict[str, Any]:
        """
        Run a validated workflow until it finishes (see ``execute_workflow``).

        Returns:
            Dictionary of results of the completed steps
        """
        workflow_name = workflow.name
        workflow.reset()

        self._notify_progress("workflow_started", f"Starting workflow: {workflow_name}", {
            "workflow_name": workflow_name,
            "steps": list(workflow.steps.keys())
        })

        results: Dict[str, Any] = {}
        task_step_map: Dict[str, str] = {}  # Maps task_id to step_name
        deadline = time.monotonic() + timeout if timeout is not None else None

        try:
            while not workflow.is_complete():
                # Check the deadline before submitting so no new work is
                # queued once the caller has stopped waiting for it.
                if deadline is not None and time.monotonic() >= deadline:
                    unfinished = workflow.get_unfinished_steps()
                    running = self._cancel_pending_tasks(workflow, task_step_map)
                    logger.error(
                        f"Workflow {workflow_name} timed out; unfinished steps: {unfinished}"
                    )
                    self._notify_progress("workflow_timed_out",
                                          f"Workflow {workflow_name} timed out", {
                        "workflow_name": workflow_name,
                        "unfinished_steps": unfinished,
                        "running_steps": running,
                        "results": results
                    })
                    raise WorkflowTimeoutError(workflow_name, unfinished, results, running)

                for step_name in workflow.get_ready_steps():
                    task_id = self._submit_workflow_step(workflow, step_name,
                                                         initial_data, results)
                    task_step_map[task_id] = step_name

                # Don't sleep past the deadline.
                pause = self.polling_interval
                if deadline is not None:
                    pause = max(0.0, min(pause, deadline - time.monotonic()))
                time.sleep(pause)

                self._poll_workflow_tasks(workflow, task_step_map, results)
        except WorkflowTimeoutError:
            raise
        except BaseException as e:
            # Queue errors (e.g. a locked database, data that is not JSON
            # serialisable) and interrupts: don't leave queued tasks behind.
            logger.error(f"Workflow {workflow_name} aborted: {e!r}; in-flight "
                         f"tasks: {task_step_map}", exc_info=True)
            running = self._cancel_pending_tasks(workflow, task_step_map)
            self._notify_progress("workflow_aborted", f"Workflow {workflow_name} aborted: {e}", {
                "workflow_name": workflow_name,
                "error": repr(e),
                "running_steps": running,
                "results": results
            })
            raise

        succeeded = not workflow.failed_steps and not workflow.skipped_steps
        if succeeded:
            message = f"Workflow {workflow_name} completed"
        else:
            message = (f"Workflow {workflow_name} finished with "
                       f"{len(workflow.failed_steps)} failed and "
                       f"{len(workflow.skipped_steps)} skipped step(s)")
            logger.warning(message)
        self._notify_progress("workflow_completed", message, {
            "workflow_name": workflow_name,
            "success": succeeded,
            "completed_steps": list(workflow.completed_steps),
            "failed_steps": list(workflow.failed_steps),
            "skipped_steps": list(workflow.skipped_steps),
            "results": results
        })

        return results

    def _start_agent_thread(self, agent_type: str, agent: BaseAgent) -> None:
        """Start the background thread that processes one agent type's tasks."""
        thread = threading.Thread(
            target=self._process_agent_tasks,
            args=(agent_type, agent),
            daemon=True,
            name=f"AgentProcessor-{agent_type}"
        )
        thread.start()
        self._processing_threads.append(thread)
        self._agent_threads[agent_type] = thread

    def _agent_types_without_workers(self, agent_types: List[str]) -> List[str]:
        """Return, sorted, the given agent types with no live processing thread."""
        idle: Set[str] = set()
        for agent_type in agent_types:
            # One .get(): stop_processing() may clear the map from another thread.
            thread = self._agent_threads.get(agent_type)
            if thread is None or not thread.is_alive():
                idle.add(agent_type)
        return sorted(idle)

    def start_processing(self):
        """Start background processing threads for all registered agents.

        Agents registered later get their thread when they are registered.
        """
        if self._processing_started:
            logger.warning("Processing already started")
            return

        self._stop_processing.clear()
        self._processing_started = True

        for agent_type, agent in self.agents.items():
            self._start_agent_thread(agent_type, agent)

        logger.info(f"Started {len(self._processing_threads)} agent processing threads")

    def stop_processing(self, timeout: float = 30.0):
        """Stop background processing threads."""
        self._stop_processing.set()
        self._processing_started = False

        # Wait for threads to finish
        for thread in self._processing_threads:
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not stop gracefully")

        self._processing_threads.clear()
        self._agent_threads.clear()
        logger.info("Stopped agent processing")
    
    def _process_agent_tasks(self, agent_type: str, agent: BaseAgent):
        """Process tasks for a specific agent type."""
        logger.info(f"Started processing tasks for agent: {agent_type}")
        
        while not self._stop_processing.is_set():
            try:
                task = self.queue.get_next_task(agent_type)
                if task is None:
                    time.sleep(self.polling_interval)
                    continue
                
                self._notify_progress("task_started", f"Processing task {task.id}", {
                    "task_id": task.id,
                    "agent_type": agent_type,
                    "method_name": task.method_name
                })
                
                # Execute the task
                method = getattr(agent, task.method_name, None)
                if method is None:
                    error_msg = f"Method {task.method_name} not found on agent {agent_type}"
                    logger.error(error_msg)
                    self.queue.fail_task(task.id, error_msg, retry=False)
                    continue
                
                try:
                    # Call the agent method with task data
                    result = method(**task.data)
                    
                    # Handle different result types
                    if hasattr(result, '__dict__'):
                        # Convert dataclass/object to dict
                        result_dict = result.__dict__ if hasattr(result, '__dict__') else {}
                    elif isinstance(result, dict):
                        result_dict = result
                    else:
                        # Wrap primitive results
                        result_dict = {"result": result}
                    
                    self.queue.complete_task(task.id, result_dict)
                    
                    self._notify_progress("task_completed", f"Task {task.id} completed", {
                        "task_id": task.id,
                        "agent_type": agent_type,
                        "result": result_dict
                    })
                    
                except Exception as e:
                    error_msg = f"Task execution failed: {str(e)}"
                    logger.error(f"Task {task.id} failed: {error_msg}")
                    self.queue.fail_task(task.id, error_msg)
                    
                    self._notify_progress("task_failed", f"Task {task.id} failed", {
                        "task_id": task.id,
                        "agent_type": agent_type,
                        "error": error_msg
                    })
            
            except Exception as e:
                logger.error(f"Error in task processing loop for {agent_type}: {e}")
                time.sleep(self.polling_interval * 2)  # Back off on errors
    
    def wait_for_completion(self, task_ids: List[str], timeout: Optional[float] = None) -> Dict[str, QueueTask]:
        """
        Wait for specific tasks to complete.
        
        Args:
            task_ids: List of task IDs to wait for
            timeout: Maximum time to wait (seconds)
            
        Returns:
            Dictionary mapping task_id to final task status
        """
        start_time = time.time()
        results: Dict[str, QueueTask] = {}

        while len(results) < len(task_ids):
            if timeout and (time.time() - start_time) > timeout:
                break
            
            for task_id in task_ids:
                if task_id not in results:
                    task = self.queue.get_task_status(task_id)
                    if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                        results[task_id] = task
            
            time.sleep(self.polling_interval)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        overall_stats = self.queue.get_queue_stats()
        
        agent_stats = {}
        for agent_type in self.agents.keys():
            agent_stats[agent_type] = self.queue.get_queue_stats(agent_type)
        
        return {
            "overall": overall_stats,
            "by_agent": agent_stats,
            "active_workflows": len(self.active_workflows),
            "registered_agents": len(self.agents),
            "processing_threads": len(self._processing_threads)
        }
    
    def cleanup(self, older_than_hours: int = 24):
        """Clean up old completed tasks."""
        self.queue.cleanup_completed_tasks(older_than_hours)