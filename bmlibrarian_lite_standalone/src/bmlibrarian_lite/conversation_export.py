"""
Conversation export utilities for BMLibrarian Lite.

Pure functions for exporting conversation history to different formats:
- export_conversation_to_json(): Export conversation as JSON
- export_conversation_to_markdown(): Export conversation as Markdown
- format_conversation_message(): Format a single message for export

Usage:
    from bmlibrarian_lite.conversation_export import (
        export_conversation_to_json,
        export_conversation_to_markdown,
    )

    # Export to JSON
    json_content = export_conversation_to_json(
        messages=conversation_history,
        document_title="paper.pdf",
    )

    # Export to Markdown
    md_content = export_conversation_to_markdown(
        messages=conversation_history,
        document_title="paper.pdf",
    )
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def export_conversation_to_json(
    messages: List[Dict[str, Any]],
    document_title: str = "",
    export_time: Optional[datetime] = None,
) -> str:
    """
    Export conversation history as formatted JSON string.

    Creates a JSON document with metadata and message history.

    Args:
        messages: List of message dictionaries with 'role', 'content', 'timestamp'
        document_title: Title of the document being discussed
        export_time: Timestamp for export (default: current time)

    Returns:
        Formatted JSON string with indentation

    Example:
        messages = [
            {"role": "user", "content": "What is the main finding?", "timestamp": "..."},
            {"role": "assistant", "content": "The study found...", "timestamp": "..."},
        ]
        json_str = export_conversation_to_json(messages, "paper.pdf")
    """
    if export_time is None:
        export_time = datetime.now()

    export_data = {
        "metadata": {
            "exported_at": export_time.isoformat(),
            "document": document_title,
            "message_count": len(messages)
        },
        "messages": messages
    }

    return json.dumps(export_data, indent=2, ensure_ascii=False)


def export_conversation_to_markdown(
    messages: List[Dict[str, Any]],
    document_title: str = "",
    export_time: Optional[datetime] = None,
) -> str:
    """
    Export conversation history as formatted Markdown string.

    Creates a Markdown document with metadata section and formatted messages.

    Args:
        messages: List of message dictionaries with 'role', 'content'
        document_title: Title of the document being discussed
        export_time: Timestamp for export (default: current time)

    Returns:
        Formatted Markdown string

    Example:
        messages = [
            {"role": "user", "content": "What is the main finding?"},
            {"role": "assistant", "content": "The study found..."},
        ]
        md_str = export_conversation_to_markdown(messages, "paper.pdf")
    """
    if export_time is None:
        export_time = datetime.now()

    lines = [
        "# Document Q&A Conversation",
        "",
        "## Metadata",
        "",
        f"- **Exported:** {export_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Document:** {document_title}",
        f"- **Messages:** {len(messages)}",
        "",
        "## Conversation",
        "",
    ]

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "user":
            lines.append("### You")
        else:
            lines.append("### AI")

        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def save_conversation_json(
    messages: List[Dict[str, Any]],
    file_path: Path,
    document_title: str = "",
) -> None:
    """
    Save conversation history to a JSON file.

    Args:
        messages: List of message dictionaries
        file_path: Path to output JSON file
        document_title: Title of the document being discussed

    Raises:
        OSError: If file cannot be written
    """
    content = export_conversation_to_json(messages, document_title)
    file_path.write_text(content, encoding='utf-8')


def save_conversation_markdown(
    messages: List[Dict[str, Any]],
    file_path: Path,
    document_title: str = "",
) -> None:
    """
    Save conversation history to a Markdown file.

    Args:
        messages: List of message dictionaries
        file_path: Path to output Markdown file
        document_title: Title of the document being discussed

    Raises:
        OSError: If file cannot be written
    """
    content = export_conversation_to_markdown(messages, document_title)
    file_path.write_text(content, encoding='utf-8')


def create_conversation_message(
    role: str,
    content: str,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Create a conversation message dictionary with consistent structure.

    Args:
        role: Message role ('user' or 'assistant')
        content: Message content text
        timestamp: Message timestamp (default: current time)

    Returns:
        Message dictionary with role, content, and timestamp

    Example:
        msg = create_conversation_message("user", "What is the main finding?")
        # {"role": "user", "content": "What is...", "timestamp": "2024-..."}
    """
    if timestamp is None:
        timestamp = datetime.now()

    return {
        "role": role,
        "content": content,
        "timestamp": timestamp.isoformat(),
    }
