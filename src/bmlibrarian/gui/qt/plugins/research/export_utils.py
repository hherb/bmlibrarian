"""
Export utilities for the Research Tab.

This module contains pure functions for file I/O operations,
including safe file writing and standardized success/error dialogs.
"""

import errno
import json
import logging
import os
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QWidget, QMessageBox, QFileDialog


def safe_write_file(
    filename: str,
    content: str,
    file_type: str = "file"
) -> tuple[bool, Optional[str]]:
    """
    Safely write content to a file with comprehensive error handling.

    Args:
        filename: Path to the file to write
        content: Content to write
        file_type: Type of file being written (for error messages)

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Get parent directory (use '.' if empty for current directory)
        parent_dir = os.path.dirname(filename)
        if not parent_dir:
            parent_dir = '.'

        # Check if parent directory exists
        if not os.path.exists(parent_dir):
            return False, f"Directory does not exist: {parent_dir}"

        # Check if we have write permissions on the directory
        if not os.access(parent_dir, os.W_OK):
            return False, f"No write permission for directory: {parent_dir}"

        # Check if file exists and we can overwrite it
        if os.path.exists(filename) and not os.access(filename, os.W_OK):
            return False, f"No write permission for file: {filename}"

        # Try to write the file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

        return True, None

    except OSError as e:
        # Handle specific OS errors
        if e.errno == errno.ENOSPC:
            return False, "No space left on device"
        elif e.errno == errno.EROFS:
            return False, "Read-only file system"
        elif e.errno == errno.EACCES:
            return False, "Permission denied"
        elif e.errno == errno.ENAMETOOLONG:
            return False, "Filename is too long"
        elif e.errno == errno.ENOENT:
            return False, f"Directory not found: {os.path.dirname(filename) or '.'}"
        else:
            return False, f"OS error: {str(e)}"
    except UnicodeEncodeError as e:
        return False, f"Encoding error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def show_save_success(
    parent: QWidget,
    filename: str,
    content: str,
    file_type: str = "Report",
    logger: Optional[logging.Logger] = None,
    status_callback: Optional[callable] = None
) -> None:
    """
    Show a standardized success message for file saves.

    Args:
        parent: Parent widget for the message box
        filename: Path to the saved file
        content: Content that was saved
        file_type: Type of file saved (for display)
        logger: Optional logger for logging
        status_callback: Optional callback to emit status message
    """
    file_size = len(content.encode('utf-8'))
    file_size_kb = file_size / 1024

    # Calculate word count for text content
    word_count = len(content.split()) if isinstance(content, str) else "N/A"

    message_parts = [
        f"{file_type} saved successfully!\n",
        f"File: {filename}",
        f"Size: {file_size_kb:.1f} KB"
    ]

    if word_count != "N/A":
        message_parts.append(f"Words: ~{word_count}")

    QMessageBox.information(
        parent,
        f"{file_type} Saved",
        "\n".join(message_parts)
    )

    if logger:
        logger.info(f"{file_type} saved to: {filename} ({file_size_kb:.1f} KB)")

    if status_callback:
        status_callback(f"{file_type} saved to {filename}")


def show_save_error(
    parent: QWidget,
    error_msg: str,
    file_type: str = "file",
    logger: Optional[logging.Logger] = None
) -> None:
    """
    Show a standardized error message for file save failures.

    Args:
        parent: Parent widget for the message box
        error_msg: Error message to display
        file_type: Type of file being saved (for display)
        logger: Optional logger for error logging
    """
    QMessageBox.critical(
        parent,
        "Save Error",
        f"An error occurred while saving the {file_type}:\n\n{error_msg}"
    )

    if logger:
        logger.error(f"Error saving {file_type}: {error_msg}")


def save_markdown_report(
    parent: QWidget,
    report_content: str,
    logger: Optional[logging.Logger] = None,
    status_callback: Optional[callable] = None
) -> bool:
    """
    Save a markdown report to file with user dialog.

    Args:
        parent: Parent widget for dialogs
        report_content: Markdown content to save
        logger: Optional logger
        status_callback: Optional callback to emit status message

    Returns:
        True if save was successful, False otherwise
    """
    if not report_content:
        QMessageBox.warning(
            parent,
            "No Report Available",
            "No final report is available to save.\n\n"
            "Please complete a research workflow first."
        )
        return False

    # Generate default filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"bmlibrarian_report_{timestamp}.md"

    # Show save file dialog
    filename, _ = QFileDialog.getSaveFileName(
        parent,
        "Save Research Report",
        default_filename,
        "Markdown Files (*.md);;All Files (*)"
    )

    if not filename:
        # User cancelled
        return False

    # Save the report using safe write helper
    success, error_msg = safe_write_file(filename, report_content, "markdown report")

    if success:
        show_save_success(
            parent, filename, report_content,
            "Research Report", logger, status_callback
        )
        return True
    else:
        show_save_error(parent, error_msg, "markdown report", logger)
        return False


def export_json_report(
    parent: QWidget,
    results: dict,
    report_content: str,
    logger: Optional[logging.Logger] = None,
    status_callback: Optional[callable] = None
) -> bool:
    """
    Export research results to JSON file with user dialog.

    Args:
        parent: Parent widget for dialogs
        results: Research results dictionary
        report_content: Final report markdown content
        logger: Optional logger
        status_callback: Optional callback to emit status message

    Returns:
        True if export was successful, False otherwise
    """
    logger = logger or logging.getLogger(__name__)

    # Validate that we have results
    if not results:
        QMessageBox.warning(
            parent,
            "No Results Available",
            "No research results are available to export.\n\n"
            "Please complete a research workflow first."
        )
        return False

    # Validate that we have a final report
    if not report_content:
        QMessageBox.warning(
            parent,
            "No Report Available",
            "No final report is available to export.\n\n"
            "Please complete the report generation step first."
        )
        return False

    # Generate default filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"bmlibrarian_results_{timestamp}.json"

    # Show save file dialog
    filename, _ = QFileDialog.getSaveFileName(
        parent,
        "Export Results as JSON",
        default_filename,
        "JSON Files (*.json);;All Files (*)"
    )

    if not filename:
        # User cancelled
        return False

    # Prepare export data with validated structure
    export_data = {
        'research_question': results.get('question', ''),
        'document_count': results.get('document_count', 0),
        'citation_count': results.get('citation_count', 0),
        'final_report_markdown': report_content,
        'generated_at': datetime.now().isoformat(),
        'workflow_status': results.get('status', 'unknown')
    }

    # Validate export data structure
    if not export_data['research_question']:
        logger.warning("Exporting JSON with empty research question")
    if not export_data['final_report_markdown']:
        logger.warning("Exporting JSON with empty final report")

    try:
        # Serialize to JSON string
        json_content = json.dumps(export_data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        show_save_error(parent, f"Failed to serialize data to JSON: {str(e)}", "JSON export", logger)
        return False

    # Save the JSON using safe write helper
    success, error_msg = safe_write_file(filename, json_content, "JSON export")

    if success:
        show_save_success(
            parent, filename, json_content,
            "Research Results", logger, status_callback
        )
        return True
    else:
        show_save_error(parent, error_msg, "JSON export", logger)
        return False
