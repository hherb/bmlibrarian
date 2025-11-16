"""PySide6-based GUI for BMLibrarian.

This package provides a modern, plugin-based Qt GUI for BMLibrarian with
support for multiple specialized interfaces through a tabbed plugin architecture.
"""

from .core.application import BMLibrarianApplication, main

__all__ = ["BMLibrarianApplication", "main"]
