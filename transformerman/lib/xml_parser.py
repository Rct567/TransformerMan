"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import re


from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from anki.notes import NoteId


def notes_from_xml(xml_response: str) -> dict[NoteId, dict[str, str]]:
    """
    Parse XML-like LM response and extract field updates by note ID.

    Args:
        xml_response: The XML-like response from the LM containing filled notes.

    Returns:
        Dictionary mapping note IDs to dictionaries of field updates.
        Example: {123: {"Front": "Hello", "Back": "World"}}

    Raises:
        ValueError: If the XML response is malformed or cannot be parsed.
    """

    try:
        # Find all note blocks
        note_pattern = r'<note nid="(\d+)"[^>]*>(.*?)</note>'
        notes = re.findall(note_pattern, xml_response, re.DOTALL)

        if not notes:
            return {}

        result: dict[NoteId, dict[str, str]] = {}

        for nid, note_content in notes:
            # Find all fields within this note
            field_pattern = r'<field name="([^"]+)">([^<]*)</field>'
            fields = re.findall(field_pattern, note_content)

            if fields:
                # NoteId is an int at runtime, so casting to int is sufficient
                # but for type checking we treat it as NoteId
                result[cast("NoteId", int(nid))] = {field_name: field_value for field_name, field_value in fields}

        return result

    except Exception as e:
        raise ValueError(f"Failed to parse XML response: {e}") from e


def escape_xml_content(content: str) -> str:
    """
    Escape special XML characters in content.

    Args:
        content: The content to escape.

    Returns:
        Escaped content safe for XML.
    """
    return (
        content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def unescape_xml_content(content: str) -> str:
    """
    Unescape XML entities in content.

    Args:
        content: The content to unescape.

    Returns:
        Unescaped content.
    """
    return (
        content.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )
