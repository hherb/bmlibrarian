"""
Agent orchestration system for managing complex multi-agent workflows.

Provides coordination between agents, handover management, and workflow execution
with progress tracking and error recovery.
"""

from typing import Dict, Any, List, Optional, Callable, Iterator
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class Workflow:
    """Defines a multi-step workflow with dependencies."""
    
    def __init__(self, name: str):
        self.name = name
        self.steps: Dict[str, WorkflowStep] = {}
        self.completed_steps: set = set()
        self.failed_steps: set = set()
    
    def add_step(self, name: str, step: WorkflowStep):
        """Add a step to the workflow."""
        self.steps[name] = step
    
    def get_ready_steps(self) -> List[str]:
        """Get steps that are ready to execute (dependencies satisfied)."""
        ready = []
        for name, step in self.steps.items():
            if (name not in self.completed_steps and 
                name not in self.failed_steps and
                all(dep in self.completed_steps for dep in step.depends_on)):
                ready.append(name)
        return ready
    
    def mark_completed(self, step_name: str):
        """Mark a step as completed."""
        self.completed_steps.add(step_name)
    
    def mark_failed(self, step_name: str):
        """Mark a step as failed."""
        self.failed_steps.add(step_name)
    
    def is_complete(self) -> bool:
        """Check if workflow is complete."""
        return len(self.completed_steps) + len(self.failed_steps) == len(self.steps)


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
        self._processing_threads: List[threading.Thread] = []
    
    def register_agent(self, agent_type: str, agent: BaseAgent):
        """Register an agent for task processing."""
        self.agents[agent_type] = agent
        logger.info(f"Registered agent: {agent_type}")
    
    def add_progress_callback(self, callback: Callable[[str, str, Any], None]):
        """Add a progress tracking callback."""
        self.progress_callbacks.append(callback)
    
    def _notify_progress(self, event_type: str, message: str, data: Any = None):
        """Notify all progress callbacks."""
        for callback in self.progress_callbacks:
            try:
                callback(event_type, message, data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
    
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
    
    def execute_workflow(self, workflow_name: str, initial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a workflow with dependency management.
        
        Args:
            workflow_name: Name of workflow to execute
            initial_data: Initial data for workflow steps
            
        Returns:
            Dictionary of step results
        """
        workflow = self.active_workflows.get(workflow_name)
        if not workflow:
            raise ValueError(f"Workflow {workflow_name} not found")
        
        self._notify_progress("workflow_started", f"Starting workflow: {workflow_name}", {
            "workflow_name": workflow_name,
            "steps": list(workflow.steps.keys())
        })
        
        results = {}
        task_step_map = {}  # Maps task_id to step_name
        
        # Submit initial ready steps
        ready_steps = workflow.get_ready_steps()
        for step_name in ready_steps:
            step = workflow.steps[step_name]
            
            # Prepare step data (combine initial data with previous results)
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
            task_step_map[task_id] = step_name
        
        # Wait for completion and submit dependent steps
        while not workflow.is_complete():
            time.sleep(self.polling_interval)
            
            # Check completed tasks
            completed_tasks = []
            for task_id, step_name in task_step_map.items():
                task_status = self.queue.get_task_status(task_id)
                if task_status and task_status.status == TaskStatus.COMPLETED:
                    results[step_name] = task_status.result
                    workflow.mark_completed(step_name)
                    completed_tasks.append(task_id)
                    self._notify_progress("workflow_step_completed", 
                                        f"Step {step_name} completed", {
                        "workflow_name": workflow_name,
                        "step_name": step_name,
                        "result": task_status.result
                    })
                elif task_status and task_status.status == TaskStatus.FAILED:
                    workflow.mark_failed(step_name)
                    completed_tasks.append(task_id)
                    self._notify_progress("workflow_step_failed", 
                                        f"Step {step_name} failed: {task_status.error_message}", {
                        "workflow_name": workflow_name,
                        "step_name": step_name,
                        "error": task_status.error_message
                    })
            
            # Remove completed tasks from tracking
            for task_id in completed_tasks:
                del task_step_map[task_id]
            
            # Submit newly ready steps
            ready_steps = workflow.get_ready_steps()
            for step_name in ready_steps:
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
                task_step_map[task_id] = step_name
        
        self._notify_progress("workflow_completed", f"Workflow {workflow_name} completed", {
            "workflow_name": workflow_name,
            "completed_steps": list(workflow.completed_steps),
            "failed_steps": list(workflow.failed_steps),
            "results": results
        })
        
        return results
    
    def start_processing(self):
        """Start background processing threads for all registered agents."""
        if self._processing_threads:
            logger.warning("Processing already started")
            return
        
        self._stop_processing.clear()
        
        for agent_type, agent in self.agents.items():
            thread = threading.Thread(
                target=self._process_agent_tasks,
                args=(agent_type, agent),
                daemon=True,
                name=f"AgentProcessor-{agent_type}"
            )
            thread.start()
            self._processing_threads.append(thread)
        
        logger.info(f"Started {len(self._processing_threads)} agent processing threads")
    
    def stop_processing(self, timeout: float = 30.0):
        """Stop background processing threads."""
        self._stop_processing.set()
        
        # Wait for threads to finish
        for thread in self._processing_threads:
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not stop gracefully")
        
        self._processing_threads.clear()
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
        results = {}
        
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