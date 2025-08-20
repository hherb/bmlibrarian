#!/usr/bin/env python3
"""
Agent Queue System Demo

Demonstrates the SQLite-based queuing system for processing large numbers
of documents efficiently with memory management and progress tracking.

This example shows:
1. Setting up the orchestrator and agents
2. Processing thousands of documents via queue
3. Progress monitoring and error handling
4. Memory-efficient batch processing
5. Workflow coordination between agents

Usage:
    python examples/queue_demo.py
"""

import os
import sys
import time
from datetime import date
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, AgentOrchestrator, 
    QueueManager, TaskPriority, TaskStatus
)


def progress_callback(event_type: str, message: str, data=None):
    """Progress callback for tracking orchestrator events."""
    timestamp = time.strftime("%H:%M:%S")
    if data and isinstance(data, dict):
        if "count" in data:
            print(f"[{timestamp}] {event_type}: {message} (count: {data['count']})")
        elif "task_id" in data:
            print(f"[{timestamp}] {event_type}: {message}")
        else:
            print(f"[{timestamp}] {event_type}: {message}")
    else:
        print(f"[{timestamp}] {event_type}: {message}")


def setup_orchestrator():
    """Set up the orchestrator with agents and progress tracking."""
    print("🔧 Setting up orchestrator and agents...")
    
    # Create orchestrator (uses default SQLite queue)
    orchestrator = AgentOrchestrator(max_workers=4, polling_interval=0.5)
    orchestrator.add_progress_callback(progress_callback)
    
    # Create and register agents
    query_agent = QueryAgent(orchestrator=orchestrator)
    scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
    
    orchestrator.register_agent("query_agent", query_agent)
    orchestrator.register_agent("document_scoring_agent", scoring_agent)
    
    return orchestrator, query_agent, scoring_agent


def demo_basic_queue_operations():
    """Demonstrate basic queue operations."""
    print("\n" + "="*60)
    print("🔄 Basic Queue Operations Demo")
    print("="*60)
    
    # Create a simple queue manager
    queue = QueueManager(":memory:")  # In-memory for demo
    
    print("1. Adding tasks to queue...")
    
    # Add some test tasks
    task_ids = []
    for i in range(5):
        task_id = queue.add_task(
            target_agent="test_agent",
            method_name="process_item",
            data={"item_id": i, "content": f"Item {i}"},
            priority=TaskPriority.NORMAL if i % 2 == 0 else TaskPriority.HIGH
        )
        task_ids.append(task_id)
    
    print(f"   Added {len(task_ids)} tasks")
    
    # Show queue stats
    stats = queue.get_queue_stats()
    print(f"   Queue stats: {dict(stats)}")
    
    print("\n2. Processing tasks in priority order...")
    
    # Process tasks (high priority first)
    processed = 0
    while True:
        task = queue.get_next_task("test_agent")
        if not task:
            break
        
        print(f"   Processing task {task.id}: priority={task.priority.name}, data={task.data}")
        
        # Simulate processing
        time.sleep(0.1)
        
        # Complete task
        queue.complete_task(task.id, {"status": "processed", "processed_at": time.time()})
        processed += 1
    
    print(f"   Processed {processed} tasks")
    
    # Final stats
    final_stats = queue.get_queue_stats()
    print(f"   Final queue stats: {dict(final_stats)}")


def demo_document_scoring_queue():
    """Demonstrate document scoring with queue processing."""
    print("\n" + "="*60) 
    print("📊 Document Scoring Queue Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent = setup_orchestrator()
    
    try:
        # Test connection
        if not scoring_agent.test_connection():
            print("❌ Cannot connect to Ollama - skipping scoring demo")
            return
        
        print("✅ Connected to Ollama")
        
        # Create sample documents
        sample_documents = []
        topics = [
            ("COVID-19 vaccine", "COVID-19 vaccine effectiveness and safety"),
            ("diabetes treatment", "Treatment approaches for type 2 diabetes"),  
            ("cancer therapy", "Novel approaches to cancer immunotherapy"),
            ("heart disease", "Cardiovascular risk factors and prevention"),
            ("brain research", "Neuroscience advances in Alzheimer's disease")
        ]
        
        for i, (topic, description) in enumerate(topics):
            for j in range(3):  # 3 docs per topic
                sample_documents.append({
                    "id": i * 3 + j + 1,
                    "title": f"Study {j+1}: {description}",
                    "abstract": f"This research paper investigates {description.lower()}. " + 
                               f"We conducted a comprehensive analysis with {100 + j*50} participants. " +
                               f"Results show significant findings related to {topic.lower()}.",
                    "authors": [f"Author {j+1}", "Co-author A"],
                    "publication_date": f"2023-0{(i*3+j) % 9 + 1}-15",
                    "pmid": f"123456{i*3+j+1:02d}"
                })
        
        print(f"📄 Created {len(sample_documents)} sample documents")
        
        # Start background processing
        print("🚀 Starting background processing...")
        orchestrator.start_processing()
        
        question = "COVID-19 vaccine effectiveness and safety"
        print(f"❓ Question: {question}")
        
        print("\n1. Submitting documents for scoring via queue...")
        
        # Submit scoring tasks with progress tracking
        task_ids = scoring_agent.submit_scoring_tasks(
            user_question=question,
            documents=sample_documents,
            priority=TaskPriority.HIGH
        )
        
        if not task_ids:
            print("❌ Failed to submit tasks to queue")
            return
        
        print(f"   ✅ Submitted {len(task_ids)} scoring tasks")
        
        # Monitor progress
        print("\n2. Monitoring task progress...")
        start_time = time.time()
        
        last_status = None
        
        while True:
            stats = orchestrator.get_stats()
            overall = stats["overall"]
            
            completed = overall.get("completed", 0)
            failed = overall.get("failed", 0)
            processing = overall.get("processing", 0)
            pending = overall.get("pending", 0)
            
            current_status = (completed, processing, pending, failed)
            
            # Only print if status changed
            if current_status != last_status:
                print(f"   📊 Status: {completed} completed, {processing} processing, "
                      f"{pending} pending, {failed} failed")
                last_status = current_status
            
            if completed + failed >= len(task_ids):
                break
            
            time.sleep(1)
        
        # Wait for all tasks to complete
        print("\n3. Waiting for task completion...")
        results = orchestrator.wait_for_completion(task_ids, timeout=30.0)
        
        processing_time = time.time() - start_time
        print(f"   ⏱️  Total processing time: {processing_time:.1f} seconds")
        
        # Collect and display results
        print("\n4. Collecting results...")
        scored_documents = []
        
        for task_id, task in results.items():
            if task.status == TaskStatus.COMPLETED and task.result:
                # Find the corresponding document
                task_idx = task_ids.index(task_id)
                doc = sample_documents[task_idx]
                
                scored_documents.append((doc, {
                    'score': task.result.get('score', 0),
                    'reasoning': task.result.get('reasoning', 'No reasoning provided')
                }))
        
        print(f"   ✅ Successfully scored {len(scored_documents)} documents")
        
        # Show top results
        print("\n5. Top scoring documents:")
        sorted_docs = sorted(scored_documents, key=lambda x: x[1]['score'], reverse=True)
        
        for i, (doc, result) in enumerate(sorted_docs[:5], 1):
            print(f"   {i}. Score: {result['score']}/5")
            print(f"      Title: {doc['title']}")
            print(f"      Reasoning: {result['reasoning']}")
            print()
        
    except Exception as e:
        print(f"❌ Error in document scoring demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("🔧 Stopping orchestrator...")
        orchestrator.stop_processing()


def demo_memory_efficient_processing():
    """Demonstrate memory-efficient processing of large document sets."""
    print("\n" + "="*60)
    print("💾 Memory-Efficient Processing Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent = setup_orchestrator()
    
    try:
        if not scoring_agent.test_connection():
            print("❌ Cannot connect to Ollama - using mock processing")
            use_mock = True
        else:
            print("✅ Connected to Ollama - using real processing")
            use_mock = False
        
        # Create a large set of documents (simulating thousands)
        print("📄 Generating large document set...")
        large_document_set = []
        
        for i in range(100):  # Simulate 100 documents (would be thousands in real use)
            large_document_set.append({
                "id": i + 1,
                "title": f"Research Paper {i+1}: Medical Study on Topic {i % 10 + 1}",
                "abstract": f"This paper presents findings from a medical study. " +
                           f"We analyzed data from {50 + (i % 100)} subjects. " +
                           f"Key findings include significant results in area {i % 5 + 1}.",
                "authors": [f"Researcher {i % 20 + 1}", "Co-researcher B"],
                "publication_date": f"2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "pmid": f"987654{i+1:03d}"
            })
        
        print(f"   Created {len(large_document_set)} documents")
        
        # Start processing
        orchestrator.start_processing()
        
        question = "medical research findings and clinical outcomes"
        
        def progress_tracker(completed, total):
            percent = (completed / total) * 100
            print(f"   📊 Progress: {completed}/{total} ({percent:.1f}%)")
        
        print(f"❓ Question: {question}")
        print("\n🔄 Processing documents with memory-efficient queue...")
        
        if use_mock:
            # Mock processing for demo without Ollama
            print("   (Using mock processing - no actual LLM calls)")
            
            results = []
            for i, doc in enumerate(large_document_set):
                # Simulate scoring
                import random
                score = random.randint(1, 5)
                reasoning = f"Mock scoring for document {i+1}"
                
                results.append((doc, {"score": score, "reasoning": reasoning}))
                
                if (i + 1) % 20 == 0:
                    progress_tracker(i + 1, len(large_document_set))
        
        else:
            # Real queue processing
            results = list(scoring_agent.process_scoring_queue(
                user_question=question,
                documents=large_document_set,
                progress_callback=progress_tracker,
                batch_size=25  # Process in smaller batches
            ))
        
        print(f"\n✅ Processed {len(results)} documents")
        
        # Analyze results
        if results:
            scores = [result[1]['score'] for result in results]
            avg_score = sum(scores) / len(scores)
            high_score_docs = [r for r in results if r[1]['score'] >= 4]
            
            print(f"\n📊 Results Analysis:")
            print(f"   Average score: {avg_score:.1f}")
            print(f"   High-scoring docs (≥4): {len(high_score_docs)}")
            print(f"   Score distribution: {dict(zip(*zip(*[(r[1]['score'], 1) for r in results])))}")
            
            if high_score_docs:
                print(f"\n🏆 Top documents:")
                sorted_docs = sorted(results, key=lambda x: x[1]['score'], reverse=True)
                for i, (doc, result) in enumerate(sorted_docs[:3], 1):
                    print(f"   {i}. {doc['title']} (Score: {result['score']}/5)")
        
    except Exception as e:
        print(f"❌ Error in memory-efficient processing demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        orchestrator.stop_processing()


def demo_queue_stats_and_monitoring():
    """Demonstrate queue statistics and monitoring capabilities."""
    print("\n" + "="*60)
    print("📈 Queue Statistics and Monitoring Demo") 
    print("="*60)
    
    queue = QueueManager(":memory:")
    
    print("1. Adding tasks with different priorities and agents...")
    
    # Add various tasks
    agents = ["query_agent", "scoring_agent", "analysis_agent"]
    priorities = [TaskPriority.LOW, TaskPriority.NORMAL, TaskPriority.HIGH, TaskPriority.URGENT]
    
    task_counts = {agent: 0 for agent in agents}
    
    for agent in agents:
        for priority in priorities:
            count = priority.value * 2  # More tasks for higher priorities
            for i in range(count):
                queue.add_task(
                    target_agent=agent,
                    method_name="process_task",
                    data={"task": i, "agent": agent, "priority": priority.name},
                    priority=priority
                )
                task_counts[agent] += 1
    
    total_tasks = sum(task_counts.values())
    print(f"   Added {total_tasks} tasks across {len(agents)} agents")
    for agent, count in task_counts.items():
        print(f"   {agent}: {count} tasks")
    
    print("\n2. Queue statistics before processing:")
    overall_stats = queue.get_queue_stats()
    print(f"   Overall: {dict(overall_stats)}")
    
    for agent in agents:
        agent_stats = queue.get_queue_stats(agent)
        print(f"   {agent}: {dict(agent_stats)}")
    
    print("\n3. Simulating partial processing...")
    
    # Process some tasks from each agent
    for agent in agents:
        processed = 0
        while processed < task_counts[agent] // 2:  # Process half
            task = queue.get_next_task(agent)
            if not task:
                break
            
            # Simulate processing time
            time.sleep(0.01)
            
            # Complete or fail task (90% success rate)
            import random
            if random.random() < 0.9:
                queue.complete_task(task.id, {"status": "completed"})
            else:
                queue.fail_task(task.id, "Simulated processing error")
            
            processed += 1
        
        print(f"   {agent}: processed {processed} tasks")
    
    print("\n4. Queue statistics after processing:")
    overall_stats = queue.get_queue_stats()
    print(f"   Overall: {dict(overall_stats)}")
    
    for agent in agents:
        agent_stats = queue.get_queue_stats(agent)
        print(f"   {agent}: {dict(agent_stats)}")
    
    print("\n5. Cleanup demonstration...")
    print(f"   Tasks before cleanup: {sum(overall_stats.values())}")
    
    # Clean up completed/failed tasks
    queue.cleanup_completed_tasks(older_than_hours=0)
    
    final_stats = queue.get_queue_stats()
    print(f"   Tasks after cleanup: {sum(final_stats.values())}")
    print(f"   Remaining: {dict(final_stats)}")


def main():
    """Run all queue system demonstrations."""
    print("🎯 Agent Queue System Demonstration")
    print("=" * 60)
    print("This demo showcases the SQLite-based queuing system for")
    print("memory-efficient, scalable agent task processing.")
    print()
    
    try:
        # Run demonstrations
        demo_basic_queue_operations()
        demo_document_scoring_queue()
        demo_memory_efficient_processing()
        demo_queue_stats_and_monitoring()
        
        print("\n" + "="*60)
        print("✅ All demonstrations completed successfully!")
        print("\nKey Benefits Demonstrated:")
        print("• Memory-efficient processing via SQLite queuing")
        print("• Scalable task orchestration and handover management")
        print("• Progress tracking and error handling")
        print("• Priority-based task scheduling")
        print("• Thread-safe concurrent processing")
        print("• Comprehensive monitoring and statistics")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()