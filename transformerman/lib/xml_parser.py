"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, MutableMapping, Sequence
from typing import TYPE_CHECKING, cast

from .field_updates import FieldUpdates
from .utilities import override

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


class NewNote(MutableMapping[str, str]):
    """
    Represents a new note to be created in Anki, parsed from XML.
    Acts like a dictionary for field access.
    """

    deck_name: str | None
    model_name: str | None
    _fields: dict[str, str]

    def __init__(
        self,
        fields: dict[str, str],
        deck_name: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._fields = fields
        self.deck_name = deck_name
        self.model_name = model_name

    @override
    def __getitem__(self, key: str) -> str:
        return self._fields[key]

    @override
    def __setitem__(self, key: str, value: str) -> None:
        self._fields[key] = value

    @override
    def __delitem__(self, key: str) -> None:
        del self._fields[key]

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    @override
    def __len__(self) -> int:
        return len(self._fields)


def new_notes_from_xml(xml_response: str) -> Sequence[NewNote]:
    """
    Parse XML-like LM response and extract new notes.

    Args:
        xml_response: The XML-like response from the LM containing new notes.

    Returns:
        Sequence of NewNote objects, each representing a new note's fields, deck and model.
    """
    # Find root deck and model if present
    root_deck_match = re.search(r'<notes[^>]*deck="([^"]+)"', xml_response)
    root_deck = root_deck_match.group(1) if root_deck_match else None

    root_model_match = re.search(r'<notes[^>]*model="([^"]+)"', xml_response)
    root_model = root_model_match.group(1) if root_model_match else None

    # Find all note blocks
    note_pattern = r"<note\b([^>]*)>(.*?)</note>"
    notes = re.findall(note_pattern, xml_response, re.DOTALL)

    result = []

    for note_attrs, note_content in notes:
        # Check for deck attribute in note tag
        note_deck_match = re.search(r'deck=["\'](.*?)["\']', note_attrs)
        deck = note_deck_match.group(1) if note_deck_match else root_deck

        # Check for model attribute in note tag
        note_model_match = re.search(r'model=["\'](.*?)["\']', note_attrs)
        model = note_model_match.group(1) if note_model_match else root_model

        # Find all fields within this note
        field_pattern = r'<field name="([^"]+)">([^<]*)</field>'
        fields = re.findall(field_pattern, note_content)

        note_fields = {}
        for field_name, field_value in fields:
            note_fields[field_name] = unescape_xml_content(field_value)

        if note_fields or deck or model:
            result.append(NewNote(fields=note_fields, deck_name=deck, model_name=model))

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
