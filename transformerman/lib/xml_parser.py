"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import html
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
    result = FieldUpdates()

    for note_attrs, note_content in _find_tags(xml_response, "note"):
        nid_str = _get_attribute(note_attrs, "nid")
        if not nid_str:
            continue

        nid = cast("NoteId", int(nid_str))
        for field_attrs, field_content in _find_tags(note_content, "field"):
            name = _get_attribute(field_attrs, "name")
            if name:
                result.add_field_update(nid, name, unescape_xml_content(field_content))

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
    # Find root notes tag to get default deck/model
    notes_match = re.search(r"<notes\b([^>]*)>", xml_response)
    root_attrs = notes_match.group(1) if notes_match else ""
    root_deck = _get_attribute(root_attrs, "deck")
    root_model = _get_attribute(root_attrs, "model")

    result = []

    for note_attrs, note_content in _find_tags(xml_response, "note"):
        deck = _get_attribute(note_attrs, "deck") or root_deck
        model = _get_attribute(note_attrs, "model") or root_model

        fields = {}
        for field_attrs, field_content in _find_tags(note_content, "field"):
            name = _get_attribute(field_attrs, "name")
            if name:
                fields[name] = unescape_xml_content(field_content)

        if fields:
            result.append(NewNote(fields=fields, deck_name=deck, model_name=model))

    return result


def _get_attribute(tag_attrs: str, attr_name: str) -> str | None:
    """Extract an attribute value from a tag's attribute string."""
    pattern = rf'{attr_name}=["\']([^"\']*)["\']'
    match = re.search(pattern, tag_attrs)
    return match.group(1) if match else None


def _find_tags(xml: str, tag_name: str) -> Iterator[tuple[str, str]]:
    """
    Find all occurrences of a tag and return its attributes and content.

    Args:
        xml: The XML string to search.
        tag_name: The name of the tag to find.

    Yields:
        Tuples of (attributes_string, content_string).
    """
    pattern = rf"<{tag_name}\b([^>]*)>(.*?)</{tag_name}>"
    for match in re.finditer(pattern, xml, re.DOTALL):
        yield match.group(1), match.group(2)


def escape_xml_content(content: str) -> str:
    """
    Escape special XML characters in content.

    Args:
        content: The content to escape.

    Returns:
        Escaped content safe for XML.
    """
    return html.escape(content, quote=True).replace("&#x27;", "&apos;")


def unescape_xml_content(content: str) -> str:
    """
    Unescape XML entities in content.

    Args:
        content: The content to unescape.

    Returns:
        Unescaped content.
    """
    return html.unescape(content)
