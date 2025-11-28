"""
Audit Validation GUI Plugin for BMLibrarian.

Provides a GUI interface for human reviewers to validate/reject automated
evaluations in the audit trail for benchmarking and fine-tuning purposes.

Note: Imports are intentionally lazy to avoid circular imports when
the plugin manager loads plugin.py directly via importlib.
"""

__all__ = [
    'AuditValidationPlugin',
    'AuditValidationDataManager',
]


def __getattr__(name: str):
    """Lazy import to avoid circular imports."""
    if name == "AuditValidationPlugin":
        from .plugin import AuditValidationPlugin
        return AuditValidationPlugin
    elif name == "AuditValidationDataManager":
        from .data_manager import AuditValidationDataManager
        return AuditValidationDataManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
