"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

import json
import re
import urllib.error
import urllib.request

from .utilities import override
from .xml_parser import notes_from_xml

import logging

if TYPE_CHECKING:
    from anki.notes import NoteId

LM_CLIENTS = {
    "dummy": "DummyLMClient",
    "openai": "OpenAILMClient",
    "claude": "ClaudeLMClient",
    "gemini": "GeminiLMClient",
}


class LmResponse:
    """Response from a language model containing the text response and parsed notes."""

    def __init__(
        self,
        text_response: str,
        error: str | None = None,
        exception: Exception | None = None
    ) -> None:
        self.text_response = text_response
        self.error = error
        self.exception = exception

    def get_notes_from_xml(self) -> dict[NoteId, dict[str, str]]:
        """Parse XML response and extract field updates by note ID."""
        if self.error is not None or self.exception is not None:
            return {}
        return notes_from_xml(self.text_response)


class LMClient(ABC):
    """Abstract base class for language model clients."""

    logger: logging.Logger
    _api_key: str
    _model: str

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self.logger = logging.getLogger(__name__)

    @property
    @abstractmethod
    def id(self) -> str:
        """Return the unique identifier for this LM client."""
        pass

    @abstractmethod
    def transform(self, prompt: str) -> LmResponse:
        pass

    @staticmethod
    @abstractmethod
    def get_available_models() -> list[str]:
        pass


class DummyLMClient(LMClient):
    """Dummy LM client that returns mock responses for testing."""

    @property
    @override
    def id(self) -> str:
        return "dummy"

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

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "mock_content_generator"
        ]


class OpenAILMClient(LMClient):

    @property
    @override
    def id(self) -> str:
        return "openai"

    @override
    def transform(self, prompt: str) -> LmResponse:
        raise NotImplementedError

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]


class ClaudeLMClient(LMClient):

    @property
    @override
    def id(self) -> str:
        return "claude"

    @override
    def transform(self, prompt: str) -> LmResponse:
        """Transform notes using Claude API."""
        if not self._api_key or not self._api_key.strip():
            raise ValueError("API key is required for ClaudeLMClient")

        # Use configured model or fall back to first available
        if self._model and self._model.strip():
            model = self._model
        else:
            model = self.get_available_models()[0]

        url = "https://api.anthropic.com/v1/messages"

        data = {
            "model": model,
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            json_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

            # Extract text from response
            try:
                content = result.get("content")
                if not content or not isinstance(content, list) or len(content) == 0:
                    raise KeyError("Missing or empty 'content' in result")
                first_content = content[0]
                text = first_content.get("text")
                if text is None:
                    raise KeyError("Missing 'text' in content")
                return LmResponse(text)
            except (KeyError, IndexError, TypeError) as e:
                self.logger.error(f"Error parsing Claude response: {e}")
                return LmResponse("", f"Error parsing AI response: {e}", e)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            self.logger.error(f"Claude HTTP Error {e.code}: {error_body}")
            return LmResponse("", f"API Error: {e.code}", e)
        except urllib.error.URLError as e:
            self.logger.error(f"Claude Network Error: {e}")
            return LmResponse("", f"Network Error: {e.reason}", e)
        except Exception as e:
            self.logger.error(f"Claude Unexpected error: {e}")
            return LmResponse("", f"Error: {e!s}", e)

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "claude-3-5-sonnet-latest",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
            "claude-opus-4-5",
            "claude-sonnet-3-5",
            "claude-haiku-3-0",
        ]

class GeminiLMClient(LMClient):


    @property
    @override
    def id(self) -> str:
        return "gemini"

    @override
    def transform(self, prompt: str) -> LmResponse:
        """Transform notes using Gemini API."""
        if not self._api_key or not self._api_key.strip():
            raise ValueError("API key is required for GeminiLMClient")

        # Use configured model or fall back to first available
        if self._model and self._model.strip():
            model = self._model
        else:
            model = self.get_available_models()[0]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        data = {"contents": [{"parts": [{"text": prompt}]}]}

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        try:
            req = urllib.request.Request(
                url, data=json.dumps(data).encode("utf-8"), headers=headers
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

            # Extract text from response
            try:
                candidates = result.get("candidates")
                if not candidates or not isinstance(candidates, list) or len(candidates) == 0:
                    raise KeyError("Missing or empty 'candidates' in result")
                candidate = candidates[0]
                content = candidate.get("content")
                if not content or not isinstance(content, dict):
                    raise KeyError("Missing or invalid 'content' in candidate")
                parts = content.get("parts")
                if not parts or not isinstance(parts, list) or len(parts) == 0:
                    raise KeyError("Missing or empty 'parts' in content")
                part = parts[0]
                text = part.get("text")
                if text is None:
                    raise KeyError("Missing 'text' in part")
                return LmResponse(text)
            except (KeyError, IndexError, TypeError) as e:
                self.logger.error(f"Error parsing Gemini response: {e}")
                return LmResponse("", f"Error parsing AI response: {e}", e)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            self.logger.error(f"Gemini HTTP Error {e.code}: {error_body}")
            return LmResponse("", f"API Error: {e.code}", e)
        except urllib.error.URLError as e:
            self.logger.error(f"Gemini Network Error: {e}")
            return LmResponse("", f"Network Error: {e.reason}", e)
        except Exception as e:
            self.logger.error(f"Gemini Unexpected error: {e}")
            return LmResponse("", f"Error: {e!s}", e)

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "gemini-flash-latest",
            "gemini-2.5-flash",
        ]


from typing import Optional


def create_lm_client(name: str, api_key: str, model: str) -> Optional[LMClient]:
    if name not in LM_CLIENTS:
        return None
    cls_name = LM_CLIENTS[name]
    cls = globals().get(cls_name)
    if cls is None:
        return None
    return cls(api_key, model)


def get_lm_client_class(name: str) -> Optional[type[LMClient]]:
    """Return the LM client class (type) for the given client name."""
    if name not in LM_CLIENTS:
        return None
    cls_name = LM_CLIENTS[name]
    cls = globals().get(cls_name)
    return cls
