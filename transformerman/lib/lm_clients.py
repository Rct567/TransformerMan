"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

import re

from .utilities import override
from .xml_parser import notes_from_xml

if TYPE_CHECKING:
    from anki.notes import NoteId


LM_CLIENTS = {
    "dummy": "DummyLMClient",
    "openai": "OpenAILMClient",
    "claude": "ClaudeLMClient",
}


class LmResponse:
    """Response from a language model containing the raw response and parsed notes."""

    def __init__(self, raw_response: str) -> None:
        self.raw_response = raw_response

    def get_notes_from_xml(self) -> dict[NoteId, dict[str, str]]:
        """Parse XML response and extract field updates by note ID."""
        return notes_from_xml(self.raw_response)


class LMClient(ABC):
    """Abstract base class for language model clients."""

    @abstractmethod
    def transform(self, prompt: str) -> LmResponse:
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        pass


class DummyLMClient(LMClient):
    """Dummy LM client that returns mock responses for testing."""

    @override
    def transform(self, prompt: str) -> LmResponse:

        # Extract note IDs and field names from the prompt
        # This is a simple implementation that looks for empty fields

        # Find all note blocks
        note_pattern = r'<note nid="(\d+)"[^>]*>(.*?)</note>'
        notes = re.findall(note_pattern, prompt, re.DOTALL)

        if not notes:
            return LmResponse('<notes></notes>')

        # Extract model name
        model_match = re.search(r'<notes model="([^"]+)">', prompt)
        model_name = model_match.group(1) if model_match else "Unknown"

        # Build response
        response_parts = [f'<notes model="{model_name}">']

        for nid, note_content in notes:
            # Extract deck name
            deck_match = re.search(r'deck="([^"]+)"', note_content)
            deck_name = deck_match.group(1) if deck_match else ""

            response_parts.append(f'  <note nid="{nid}" deck="{deck_name}">')

            # Find all fields
            field_pattern = r'<field name="([^"]+)">([^<]*)</field>'
            fields = re.findall(field_pattern, note_content)

            for field_name, field_value in fields:
                if field_value.strip():
                    # Keep existing content
                    response_parts.append(f'    <field name="{field_name}">{field_value}</field>')
                else:
                    # Fill empty field with mock content
                    mock_content = f"Mock content for {field_name}"
                    response_parts.append(f'    <field name="{field_name}">{mock_content}</field>')

            response_parts.append('  </note>')

        response_parts.append('</notes>')

        return LmResponse('\n'.join(response_parts))

    @override
    def get_available_models(self) -> list[str]:
        return [
            "mock_content_generator"
        ]


class OpenAILMClient(LMClient):
    @override
    def transform(self, prompt: str) -> LmResponse:
        raise NotImplementedError

    @override
    def get_available_models(self) -> list[str]:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]


class ClaudeLMClient(LMClient):
    @override
    def transform(self, prompt: str) -> LmResponse:
        raise NotImplementedError

    @override
    def get_available_models(self) -> list[str]:
        return [
            "claude-3-5-sonnet-latest",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ]


def create_lm_client(name: str) -> LMClient:
    cls_name = LM_CLIENTS.get(name, "DummyLMClient")
    cls = globals().get(cls_name, DummyLMClient)
    return cls()
