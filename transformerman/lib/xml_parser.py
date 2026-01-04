"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import re

from typing import TYPE_CHECKING, cast

from .field_updates import FieldUpdates

if TYPE_CHECKING:
    from anki.notes import NoteId


def notes_from_xml(xml_response: str) -> FieldUpdates:
    """
    Parse XML-like LM response and extract field updates by note ID.

    Args:
        xml_response: The XML-like response from the LM containing filled notes.

    Returns:
        FieldUpdates instance mapping note IDs to dictionaries of field updates.
        Example: FieldUpdates({123: {"Front": "Hello", "Back": "World"}})
    """

    # Find all note blocks
    note_pattern = r'<note nid="(\d+)"[^>]*>(.*?)</note>'
    notes = re.findall(note_pattern, xml_response, re.DOTALL)

    result = FieldUpdates()

    for nid, note_content in notes:
        # Find all fields within this note
        field_pattern = r'<field name="([^"]+)">([^<]*)</field>'
        fields = re.findall(field_pattern, note_content)

        for field_name, field_value in fields:
            result.add_field_update(
                cast("NoteId", int(nid)),
                field_name,
                unescape_xml_content(field_value)
            )

    return result


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
