"""
Comprehensive Logging Configuration for BMLibrarian CLI

Provides detailed observability for all orchestration steps, database queries, 
agent operations, and workflow execution with timestamped log files.
"""

import logging
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import traceback


class BMLibrarianFormatter(logging.Formatter):
    """Custom formatter for BMLibrarian logs with structured data support."""
    
    def format(self, record):
        # Base format
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Build the log entry
        parts = [
            f"[{timestamp}]",
            f"[{record.levelname:8s}]",
            f"[{record.name}]",
        ]
        
        # Add function and line info for debug level
        if record.levelno <= logging.DEBUG:
            parts.append(f"[{record.funcName}:{record.lineno}]")
        
        # Add the main message
        message = record.getMessage()
        parts.append(message)
        
        base_message = " ".join(parts)
        
        # Add structured data if present
        if hasattr(record, 'structured_data'):
            structured_json = json.dumps(record.structured_data, indent=2, default=str)
            base_message += f"\nSTRUCTURED_DATA: {structured_json}"
        
        # Add exception info if present
        if record.exc_info:
            base_message += f"\nEXCEPTION: {self.formatException(record.exc_info)}"
        
        return base_message


class WorkflowLogger:
    """Centralized logger for workflow orchestration with structured logging."""
    
    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        self.workflow_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.step_counter = 0
        
        # Setup main logger
        self.logger = logging.getLogger('bmlibrarian')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # Clear any existing handlers
        
        # File handler with custom formatter
        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(BMLibrarianFormatter())
        
        # Console handler for important messages
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(BMLibrarianFormatter())
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Create specialized loggers for different components
        self.workflow_logger = logging.getLogger('bmlibrarian.workflow')
        self.database_logger = logging.getLogger('bmlibrarian.database')
        self.agent_logger = logging.getLogger('bmlibrarian.agents')
        self.ui_logger = logging.getLogger('bmlibrarian.ui')
        
        # Log session start
        self.log_session_start()
    
    def log_session_start(self):
        """Log the start of a new CLI session."""
        self.workflow_logger.info(
            f"BMLibrarian CLI session started",
            extra={
                'structured_data': {
                    'event_type': 'session_start',
                    'workflow_id': self.workflow_id,
                    'timestamp': datetime.now().isoformat(),
                    'log_file': self.log_file_path,
                    'python_version': sys.version,
                    'platform': sys.platform
                }
            }
        )
    
    def log_workflow_step(self, step_name: str, step_number: int, description: str, 
                         metadata: Optional[Dict[str, Any]] = None):
        """Log a workflow step with detailed metadata."""
        self.step_counter += 1
        
        step_data = {
            'event_type': 'workflow_step',
            'workflow_id': self.workflow_id,
            'step_number': step_number,
            'step_name': step_name,
            'description': description,
            'timestamp': datetime.now().isoformat(),
            'step_counter': self.step_counter
        }
        
        if metadata:
            step_data.update(metadata)
        
        self.workflow_logger.info(
            f"STEP {step_number}: {step_name} - {description}",
            extra={'structured_data': step_data}
        )
    
    def log_database_query(self, query: str, query_type: str, parameters: Optional[Dict] = None,
                          result_count: Optional[int] = None, execution_time: Optional[float] = None):
        """Log database query with parameters and results summary."""
        query_data = {
            'event_type': 'database_query',
            'workflow_id': self.workflow_id,
            'query_type': query_type,
            'query': query,
            'timestamp': datetime.now().isoformat()
        }
        
        if parameters:
            query_data['parameters'] = parameters
        if result_count is not None:
            query_data['result_count'] = result_count
        if execution_time is not None:
            query_data['execution_time_ms'] = execution_time
        
        self.database_logger.info(
            f"Database Query [{query_type}]: {query[:100]}{'...' if len(query) > 100 else ''}",
            extra={'structured_data': query_data}
        )
    
    def log_database_results(self, query_type: str, results: List[Dict[str, Any]], 
                           query_context: str = None):
        """Log complete database results for full observability."""
        results_data = {
            'event_type': 'database_results',
            'workflow_id': self.workflow_id,
            'query_type': query_type,
            'result_count': len(results),
            'timestamp': datetime.now().isoformat(),
            'results': results  # Full result set
        }
        
        if query_context:
            results_data['query_context'] = query_context
        
        self.database_logger.debug(
            f"Database Results [{query_type}]: {len(results)} rows returned",
            extra={'structured_data': results_data}
        )
        
        # Also log summary at info level
        if results:
            sample_keys = list(results[0].keys()) if results else []
            self.database_logger.info(
                f"Database Results Summary [{query_type}]: {len(results)} rows, "
                f"columns: {sample_keys}"
            )
    
    def log_agent_operation(self, agent_name: str, operation: str, input_data: Dict[str, Any],
                          output_data: Optional[Dict[str, Any]] = None, 
                          execution_time: Optional[float] = None, error: Optional[str] = None):
        """Log agent operations with input/output data."""
        agent_data = {
            'event_type': 'agent_operation',
            'workflow_id': self.workflow_id,
            'agent_name': agent_name,
            'operation': operation,
            'timestamp': datetime.now().isoformat(),
            'input_data': input_data
        }
        
        if output_data:
            agent_data['output_data'] = output_data
        if execution_time:
            agent_data['execution_time_ms'] = execution_time
        if error:
            agent_data['error'] = error
        
        level = logging.ERROR if error else logging.INFO
        message = f"Agent [{agent_name}] {operation}"
        if error:
            message += f" - ERROR: {error}"
        
        self.agent_logger.log(
            level,
            message,
            extra={'structured_data': agent_data}
        )
    
    def log_user_interaction(self, interaction_type: str, prompt: str, response: str = None,
                           auto_mode: bool = False):
        """Log user interface interactions."""
        ui_data = {
            'event_type': 'user_interaction',
            'workflow_id': self.workflow_id,
            'interaction_type': interaction_type,
            'prompt': prompt,
            'auto_mode': auto_mode,
            'timestamp': datetime.now().isoformat()
        }
        
        if response:
            ui_data['response'] = response
        
        self.ui_logger.info(
            f"UI Interaction [{interaction_type}]: {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
            extra={'structured_data': ui_data}
        )
    
    def log_configuration(self, config_data: Dict[str, Any]):
        """Log configuration settings for the session."""
        config_log_data = {
            'event_type': 'configuration',
            'workflow_id': self.workflow_id,
            'timestamp': datetime.now().isoformat(),
            'configuration': config_data
        }
        
        self.workflow_logger.info(
            "Session Configuration",
            extra={'structured_data': config_log_data}
        )
    
    def log_error(self, error_type: str, error_message: str, context: Dict[str, Any] = None,
                 exception: Exception = None):
        """Log errors with full context and stack trace."""
        error_data = {
            'event_type': 'error',
            'workflow_id': self.workflow_id,
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': datetime.now().isoformat()
        }
        
        if context:
            error_data['context'] = context
        
        if exception:
            error_data['exception_type'] = type(exception).__name__
            error_data['stack_trace'] = traceback.format_exc()
        
        self.workflow_logger.error(
            f"Error [{error_type}]: {error_message}",
            extra={'structured_data': error_data}
        )
    
    def log_performance_metrics(self, operation: str, duration: float, 
                              metrics: Dict[str, Any] = None):
        """Log performance metrics for operations."""
        perf_data = {
            'event_type': 'performance_metrics',
            'workflow_id': self.workflow_id,
            'operation': operation,
            'duration_seconds': duration,
            'timestamp': datetime.now().isoformat()
        }
        
        if metrics:
            perf_data['metrics'] = metrics
        
        self.workflow_logger.info(
            f"Performance [{operation}]: {duration:.3f}s",
            extra={'structured_data': perf_data}
        )
    
    def log_session_end(self, success: bool, summary: Dict[str, Any] = None):
        """Log the end of a CLI session with summary."""
        end_data = {
            'event_type': 'session_end',
            'workflow_id': self.workflow_id,
            'success': success,
            'timestamp': datetime.now().isoformat(),
            'total_steps': self.step_counter
        }
        
        if summary:
            end_data['summary'] = summary
        
        self.workflow_logger.info(
            f"BMLibrarian CLI session ended - {'SUCCESS' if success else 'FAILURE'}",
            extra={'structured_data': end_data}
        )


def setup_logging(log_directory: str = "logs") -> WorkflowLogger:
    """
    Setup logging for BMLibrarian CLI with timestamped log files.
    
    Args:
        log_directory: Directory to store log files (default: "logs")
        
    Returns:
        WorkflowLogger instance configured for the session
    """
    # Create log directory if it doesn't exist
    log_dir = Path(log_directory)
    log_dir.mkdir(exist_ok=True)
    
    # Generate timestamped log filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"{timestamp}_bmlibrarian.log"
    log_file_path = log_dir / log_filename
    
    # Create and return workflow logger
    return WorkflowLogger(str(log_file_path))


def get_current_logger() -> Optional[logging.Logger]:
    """Get the current BMLibrarian logger if it exists."""
    return logging.getLogger('bmlibrarian') if logging.getLogger('bmlibrarian').handlers else None