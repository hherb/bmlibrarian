"""
Threading utilities for BMLibrarian Qt GUI.

Provides worker threads and signals for running async operations.
"""

from typing import Callable, Any
from PySide6.QtCore import QObject, QRunnable, Signal, Slot, QThreadPool


class WorkerSignals(QObject):
    """
    Signals for worker threads.

    Provides standard signals for communicating worker status and results.
    """

    started = Signal()  # Emitted when worker starts
    finished = Signal()  # Emitted when worker finishes (success or error)
    error = Signal(Exception)  # Emitted on error
    result = Signal(object)  # Emitted with result object
    progress = Signal(int)  # Emitted with progress percentage (0-100)
    status = Signal(str)  # Emitted with status message


class Worker(QRunnable):
    """
    Worker thread for running tasks in background.

    Usage:
        worker = Worker(my_function, arg1, arg2, kwarg1=value1)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, fn: Callable, *args, **kwargs):
        """
        Initialize worker with function and arguments.

        Args:
            fn: Function to execute in background
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        """Execute the worker function."""
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            self.signals.finished.emit()


class ProgressWorker(QRunnable):
    """
    Worker thread with progress reporting callback.

    Usage:
        def my_task(progress_callback, status_callback):
            for i in range(100):
                progress_callback.emit(i)
                status_callback.emit(f"Processing {i}...")
            return result

        worker = ProgressWorker(my_task)
        worker.signals.progress.connect(on_progress)
        worker.signals.status.connect(on_status)
        worker.signals.result.connect(on_result)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, fn: Callable, *args, **kwargs):
        """
        Initialize progress worker.

        Args:
            fn: Function to execute. Should accept progress_callback and
                status_callback as first two arguments.
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        """Execute the worker function with progress reporting."""
        try:
            self.signals.started.emit()
            result = self.fn(
                self.signals.progress, self.signals.status, *self.args, **self.kwargs
            )
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            self.signals.finished.emit()


def create_worker(fn: Callable, *args, **kwargs) -> Worker:
    """
    Convenience function to create a worker.

    Args:
        fn: Function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Worker instance
    """
    return Worker(fn, *args, **kwargs)


def create_progress_worker(fn: Callable, *args, **kwargs) -> ProgressWorker:
    """
    Convenience function to create a progress worker.

    Args:
        fn: Function to execute (should accept progress and status callbacks)
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments

    Returns:
        ProgressWorker instance
    """
    return ProgressWorker(fn, *args, **kwargs)


def run_in_thread(fn: Callable, *args, **kwargs) -> Worker:
    """
    Run a function in a background thread.

    Args:
        fn: Function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Worker instance (already started)
    """
    worker = create_worker(fn, *args, **kwargs)
    QThreadPool.globalInstance().start(worker)
    return worker
