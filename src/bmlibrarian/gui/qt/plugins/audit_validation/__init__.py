"""
Audit Validation GUI Plugin for BMLibrarian.

Provides a GUI interface for human reviewers to validate/reject automated
evaluations in the audit trail for benchmarking and fine-tuning purposes.
"""

from .plugin import AuditValidationPlugin
from .data_manager import AuditValidationDataManager

__all__ = [
    'AuditValidationPlugin',
    'AuditValidationDataManager',
]
