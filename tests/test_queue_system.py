"""
Unit tests for the agent queuing system.

Tests QueueManager, AgentOrchestrator, and queue-aware agent methods
with comprehensive coverage of error conditions and edge cases.
"""

import pytest
import tempfile
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from bmlibrarian.agents import (
    QueueManager, AgentOrchestrator, DocumentScoringAgent, QueryAgent,
    TaskStatus, TaskPriority, Workflow, WorkflowStep
)
from bmlibrarian.agents.queue_manager import QueueTask


class TestQueueManager:
    """Test the SQLite-based QueueManager."""
    
    def setup_method(self):
        """Setup test with temporary database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.queue = QueueManager(self.temp_db.name)
    
    def teardown_method(self):
        """Cleanup temporary database."""
        import os
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass
    
    def test_add_single_task(self):
        """Test adding a single task to the queue."""
        task_id = self.queue.add_task(
            target_agent="test_agent",
            method_name="test_method",
            data={"test": "data"},
            source_agent="user",
            priority=TaskPriority.HIGH
        )
        
        assert task_id is not None
        assert len(task_id) > 0
        
        # Verify task was stored correctly
        task = self.queue.get_task_status(task_id)
        assert task.target_agent == "test_agent"
        assert task.method_name == "test_method"
        assert task.data == {"test": "data"}
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.HIGH
    
    def test_add_batch_tasks(self):
        """Test adding multiple tasks efficiently."""
        data_list = [
            {"doc_id": 1, "content": "test1"},
            {"doc_id": 2, "content": "test2"},
            {"doc_id": 3, "content": "test3"}
        ]
        
        task_ids = self.queue.add_batch_tasks(
            target_agent="scoring_agent",
            method_name="evaluate_document",
            data_list=data_list,
            priority=TaskPriority.NORMAL
        )
        
        assert len(task_ids) == 3
        
        # Verify all tasks were stored
        for i, task_id in enumerate(task_ids):
            task = self.queue.get_task_status(task_id)
            assert task.data["doc_id"] == i + 1
            assert task.status == TaskStatus.PENDING
    
    def test_get_next_task_priority_order(self):
        """Test that tasks are retrieved in priority order."""
        # Add tasks with different priorities
        low_id = self.queue.add_task("test_agent", "method", {"priority": "low"}, priority=TaskPriority.LOW)
        urgent_id = self.queue.add_task("test_agent", "method", {"priority": "urgent"}, priority=TaskPriority.URGENT)
        normal_id = self.queue.add_task("test_agent", "method", {"priority": "normal"}, priority=TaskPriority.NORMAL)
        
        # Should get urgent task first
        task1 = self.queue.get_next_task("test_agent")
        assert task1.id == urgent_id
        assert task1.status == TaskStatus.PROCESSING
        
        # Then normal
        task2 = self.queue.get_next_task("test_agent")
        assert task2.id == normal_id
        
        # Finally low
        task3 = self.queue.get_next_task("test_agent")
        assert task3.id == low_id
        
        # No more tasks
        task4 = self.queue.get_next_task("test_agent")
        assert task4 is None
    
    def test_complete_task(self):
        """Test marking a task as completed."""
        task_id = self.queue.add_task("test_agent", "test_method", {"test": "data"})
        
        # Get and complete the task
        task = self.queue.get_next_task("test_agent")
        result = {"score": 4, "reasoning": "test result"}
        self.queue.complete_task(task_id, result)
        
        # Verify task is completed
        completed_task = self.queue.get_task_status(task_id)
        assert completed_task.status == TaskStatus.COMPLETED
        assert completed_task.result == result
        assert completed_task.completed_at is not None
    
    def test_fail_task_with_retry(self):
        """Test failing a task that should be retried."""
        task_id = self.queue.add_task("test_agent", "test_method", {"test": "data"}, max_retries=2)
        
        # Get task and fail it
        task = self.queue.get_next_task("test_agent")
        self.queue.fail_task(task_id, "Test error", retry=True)
        
        # Should be reset to pending for retry
        failed_task = self.queue.get_task_status(task_id)
        assert failed_task.status == TaskStatus.PENDING
        assert failed_task.retry_count == 1
        assert failed_task.error_message == "Test error"
        
        # Should be available for retry
        retry_task = self.queue.get_next_task("test_agent")
        assert retry_task.id == task_id
    
    def test_fail_task_max_retries(self):
        """Test failing a task that has exceeded max retries."""
        task_id = self.queue.add_task("test_agent", "test_method", {"test": "data"}, max_retries=1)
        
        # Fail twice (exceeds max_retries)
        self.queue.get_next_task("test_agent")
        self.queue.fail_task(task_id, "First error", retry=True)
        
        self.queue.get_next_task("test_agent")
        self.queue.fail_task(task_id, "Second error", retry=True)
        
        # Should be permanently failed
        failed_task = self.queue.get_task_status(task_id)
        assert failed_task.status == TaskStatus.FAILED
        assert failed_task.retry_count == 2
    
    def test_queue_stats(self):
        """Test queue statistics functionality."""
        # Add various tasks
        self.queue.add_task("agent1", "method", {"test": "data"}, priority=TaskPriority.HIGH)
        self.queue.add_task("agent1", "method", {"test": "data"})
        self.queue.add_task("agent2", "method", {"test": "data"})
        
        # Get one task to mark as processing
        self.queue.get_next_task("agent1")
        
        # Check overall stats
        stats = self.queue.get_queue_stats()
        assert stats[TaskStatus.PENDING.value] == 2
        assert stats[TaskStatus.PROCESSING.value] == 1
        
        # Check agent-specific stats
        agent1_stats = self.queue.get_queue_stats("agent1")
        assert agent1_stats[TaskStatus.PENDING.value] == 1
        assert agent1_stats[TaskStatus.PROCESSING.value] == 1
    
    def test_cleanup_completed_tasks(self):
        """Test cleanup of old completed tasks."""
        # Add and complete a task
        task_id = self.queue.add_task("test_agent", "test_method", {"test": "data"})
        task = self.queue.get_next_task("test_agent")
        self.queue.complete_task(task_id, {"result": "success"})
        
        # Task should exist
        assert self.queue.get_task_status(task_id) is not None
        
        # Cleanup (with 0 hours to clean everything)
        self.queue.cleanup_completed_tasks(older_than_hours=0)
        
        # Task should be gone
        assert self.queue.get_task_status(task_id) is None
    
    def test_cancel_tasks(self):
        """Test cancelling pending tasks."""
        task1_id = self.queue.add_task("agent1", "method", {"test": "data"})
        task2_id = self.queue.add_task("agent2", "method", {"test": "data"})
        
        # Cancel tasks for agent1
        self.queue.cancel_tasks(target_agent="agent1")
        
        # Verify cancellation
        task1 = self.queue.get_task_status(task1_id)
        task2 = self.queue.get_task_status(task2_id)
        
        assert task1.status == TaskStatus.CANCELLED
        assert task2.status == TaskStatus.PENDING  # Should be unaffected


class TestAgentOrchestrator:
    """Test the AgentOrchestrator workflow management."""
    
    def setup_method(self):
        """Setup test orchestrator with temporary queue."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        self.temp_db_path = temp_db.name
        
        queue_manager = QueueManager(self.temp_db_path)
        self.orchestrator = AgentOrchestrator(queue_manager=queue_manager, max_workers=2)
        
        # Create mock agents
        self.mock_agent1 = Mock()
        self.mock_agent1.get_agent_type.return_value = "test_agent1"
        self.mock_agent1.test_method.return_value = {"result": "success1"}
        
        self.mock_agent2 = Mock()
        self.mock_agent2.get_agent_type.return_value = "test_agent2" 
        self.mock_agent2.test_method.return_value = {"result": "success2"}
        
        self.orchestrator.register_agent("test_agent1", self.mock_agent1)
        self.orchestrator.register_agent("test_agent2", self.mock_agent2)
    
    def teardown_method(self):
        """Cleanup orchestrator and temporary files."""
        self.orchestrator.stop_processing()
        import os
        try:
            os.unlink(self.temp_db_path)
        except OSError:
            pass
    
    def test_register_agent(self):
        """Test agent registration."""
        agent = Mock()
        agent.get_agent_type.return_value = "new_agent"
        
        self.orchestrator.register_agent("new_agent", agent)
        
        assert "new_agent" in self.orchestrator.agents
        assert self.orchestrator.agents["new_agent"] == agent
    
    def test_submit_single_task(self):
        """Test submitting a single task."""
        task_id = self.orchestrator.submit_task(
            target_agent="test_agent1",
            method_name="test_method",
            data={"test": "data"},
            priority=TaskPriority.HIGH
        )
        
        assert task_id is not None
        
        # Verify task in queue
        task = self.orchestrator.queue.get_task_status(task_id)
        assert task.target_agent == "test_agent1"
        assert task.method_name == "test_method"
        assert task.priority == TaskPriority.HIGH
    
    def test_submit_batch_tasks(self):
        """Test submitting multiple tasks."""
        data_list = [{"id": 1}, {"id": 2}, {"id": 3}]
        
        task_ids = self.orchestrator.submit_batch_tasks(
            target_agent="test_agent1",
            method_name="test_method",
            data_list=data_list
        )
        
        assert len(task_ids) == 3
        
        # Verify all tasks in queue
        for task_id in task_ids:
            task = self.orchestrator.queue.get_task_status(task_id)
            assert task.target_agent == "test_agent1"
            assert task.status == TaskStatus.PENDING
    
    def test_progress_callbacks(self):
        """Test progress callback functionality."""
        callback_calls = []
        
        def test_callback(event_type, message, data):
            callback_calls.append((event_type, message, data))
        
        self.orchestrator.add_progress_callback(test_callback)
        
        # Submit a task (should trigger callback)
        self.orchestrator.submit_task("test_agent1", "test_method", {"test": "data"})
        
        assert len(callback_calls) > 0
        assert any("task_submitted" in call[0] for call in callback_calls)
    
    def test_workflow_creation(self):
        """Test workflow creation and step management."""
        workflow = self.orchestrator.create_workflow("test_workflow")
        
        step1 = WorkflowStep("test_agent1", "test_method", priority=TaskPriority.HIGH)
        step2 = WorkflowStep("test_agent2", "test_method", depends_on=["step1"])
        
        workflow.add_step("step1", step1)
        workflow.add_step("step2", step2)
        
        # Test dependency resolution
        ready_steps = workflow.get_ready_steps()
        assert "step1" in ready_steps
        assert "step2" not in ready_steps  # Has unmet dependency
        
        # Complete step1
        workflow.mark_completed("step1")
        ready_steps = workflow.get_ready_steps()
        assert "step2" in ready_steps  # Dependency now satisfied
    
    def test_background_processing(self):
        """Test background task processing."""
        # Start background processing
        self.orchestrator.start_processing()
        
        # Submit a task
        task_id = self.orchestrator.submit_task(
            target_agent="test_agent1",
            method_name="test_method",
            data={"test": "data"}
        )
        
        # Wait for processing
        time.sleep(0.5)
        
        # Check if task was processed
        task = self.orchestrator.queue.get_task_status(task_id)
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.PROCESSING]
        
        # Stop processing
        self.orchestrator.stop_processing()
    
    def test_wait_for_completion(self):
        """Test waiting for specific tasks to complete."""
        # Start processing
        self.orchestrator.start_processing()
        
        # Submit tasks
        task_ids = self.orchestrator.submit_batch_tasks(
            target_agent="test_agent1",
            method_name="test_method", 
            data_list=[{"id": 1}, {"id": 2}]
        )
        
        # Wait for completion
        results = self.orchestrator.wait_for_completion(task_ids, timeout=5.0)
        
        assert len(results) == 2
        for task_id in task_ids:
            assert task_id in results
            assert results[task_id].status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
    
    def test_orchestrator_stats(self):
        """Test orchestrator statistics."""
        # Add some tasks
        self.orchestrator.submit_task("test_agent1", "test_method", {"test": "data"})
        self.orchestrator.submit_task("test_agent2", "test_method", {"test": "data"})
        
        stats = self.orchestrator.get_stats()
        
        assert "overall" in stats
        assert "by_agent" in stats
        assert "registered_agents" in stats
        assert stats["registered_agents"] == 2


class TestQueueAwareAgents:
    """Test queue integration in agents."""
    
    def setup_method(self):
        """Setup test agents with orchestrator."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        self.temp_db_path = temp_db.name
        
        queue_manager = QueueManager(self.temp_db_path)
        self.orchestrator = AgentOrchestrator(queue_manager=queue_manager)
        
    def teardown_method(self):
        """Cleanup temporary files."""
        self.orchestrator.stop_processing()
        import os
        try:
            os.unlink(self.temp_db_path)
        except OSError:
            pass
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_scoring_agent_queue_submission(self, mock_client):
        """Test DocumentScoringAgent queue task submission."""
        agent = DocumentScoringAgent(orchestrator=self.orchestrator)
        self.orchestrator.register_agent("document_scoring_agent", agent)
        
        documents = [
            {"title": "Test Doc 1", "abstract": "Test abstract 1"},
            {"title": "Test Doc 2", "abstract": "Test abstract 2"}
        ]
        
        # Submit scoring tasks
        task_ids = agent.submit_scoring_tasks("test question", documents)
        
        assert task_ids is not None
        assert len(task_ids) == 2
        
        # Verify tasks in queue
        for task_id in task_ids:
            task = self.orchestrator.queue.get_task_status(task_id)
            assert task.target_agent == "document_scoring_agent"
            assert task.method_name == "evaluate_document_from_queue"
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_scoring_agent_fallback_processing(self, mock_client):
        """Test DocumentScoringAgent fallback when no orchestrator."""
        # Mock Ollama responses
        mock_client.return_value.chat.return_value = {
            'message': {'content': '{"score": 3, "reasoning": "Test reasoning"}'}
        }
        
        agent = DocumentScoringAgent()  # No orchestrator
        
        documents = [
            {"title": "Test Doc 1", "abstract": "Test abstract 1"},
            {"title": "Test Doc 2", "abstract": "Test abstract 2"}
        ]
        
        # Process without queue (should fallback to direct processing)
        results = list(agent.process_scoring_queue("test question", documents))
        
        assert len(results) == 2
        for doc, result in results:
            assert result["score"] == 3
            assert result["reasoning"] == "Test reasoning"
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_agent_task_submission_methods(self, mock_client):
        """Test BaseAgent task submission methods."""
        agent = DocumentScoringAgent(orchestrator=self.orchestrator)
        
        # Test single task submission
        task_id = agent.submit_task(
            method_name="test_method",
            data={"test": "data"}
        )
        
        assert task_id is not None
        
        # Test batch task submission
        data_list = [{"id": 1}, {"id": 2}]
        task_ids = agent.submit_batch_tasks(
            method_name="test_method",
            data_list=data_list
        )
        
        assert task_ids is not None
        assert len(task_ids) == 2
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_agent_without_orchestrator(self, mock_client):
        """Test agent methods when no orchestrator is configured."""
        agent = DocumentScoringAgent()  # No orchestrator
        
        # Should return None for queue operations
        task_id = agent.submit_task("test_method", {"test": "data"})
        assert task_id is None
        
        task_ids = agent.submit_batch_tasks("test_method", [{"id": 1}])
        assert task_ids is None


class TestThreadSafety:
    """Test thread safety of queue operations."""
    
    def setup_method(self):
        """Setup test with temporary database."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        self.temp_db_path = temp_db.name
        self.queue = QueueManager(self.temp_db_path)
    
    def teardown_method(self):
        """Cleanup temporary database."""
        import os
        try:
            os.unlink(self.temp_db_path)
        except OSError:
            pass
    
    def test_concurrent_task_addition(self):
        """Test adding tasks from multiple threads."""
        task_ids = []
        errors = []
        
        def add_tasks():
            try:
                for i in range(10):
                    task_id = self.queue.add_task(
                        f"agent_{threading.current_thread().ident}",
                        "test_method",
                        {"thread_id": threading.current_thread().ident, "task": i}
                    )
                    task_ids.append(task_id)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=add_tasks)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(task_ids) == 30  # 3 threads * 10 tasks each
        assert len(set(task_ids)) == 30  # All unique
    
    def test_concurrent_task_processing(self):
        """Test processing tasks from multiple threads."""
        # Add tasks
        for i in range(20):
            self.queue.add_task("test_agent", "test_method", {"task": i})
        
        processed_tasks = []
        errors = []
        
        def process_tasks():
            try:
                for _ in range(5):  # Each thread processes 5 tasks
                    task = self.queue.get_next_task("test_agent")
                    if task:
                        processed_tasks.append(task.id)
                        self.queue.complete_task(task.id, {"result": "success"})
                    else:
                        break
            except Exception as e:
                errors.append(e)
        
        # Start multiple processing threads
        threads = []
        for _ in range(4):
            thread = threading.Thread(target=process_tasks)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(processed_tasks) == 20
        assert len(set(processed_tasks)) == 20  # All unique task IDs


if __name__ == "__main__":
    pytest.main([__file__])