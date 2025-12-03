"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod



class LMClient(ABC):
    """Abstract base class for language model clients."""

    @abstractmethod
    def transform(self, prompt: str) -> str:
        """
        Send a prompt to the language model and return the response.

        Args:
            prompt: The prompt to send to the LM, including examples and target notes.

        Returns:
            The LM response in XML-like format with filled fields.

        Raises:
            Exception: If the API call fails or returns an error.
        """
        pass


class DummyLMClient(LMClient):
    """Dummy LM client that returns mock responses for testing."""

    def transform(self, prompt: str) -> str:
        """
        Return a mock XML response based on the input prompt.

        This implementation extracts note IDs from the prompt and returns
        mock filled fields for testing purposes.

        Args:
            prompt: The prompt containing target notes to fill.

        Returns:
            Mock XML response with filled fields.
        """
        # Extract note IDs and field names from the prompt
        # This is a simple implementation that looks for empty fields
        import re

        # Find all note blocks
        note_pattern = r'<note nid="(\d+)"[^>]*>(.*?)</note>'
        notes = re.findall(note_pattern, prompt, re.DOTALL)

        if not notes:
            return '<notes></notes>'

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

        return '\n'.join(response_parts)
