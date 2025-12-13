"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType, Callable, Optional
from abc import ABC, abstractmethod

import re
import requests

from .utilities import override
from .xml_parser import notes_from_xml
from .http_utils import make_api_request_json, ProgressData

import logging

ApiKey = NewType('ApiKey', str)
ModelName = NewType('ModelName', str)

if TYPE_CHECKING:
    from anki.notes import NoteId
    from typing import Optional


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
    _api_key: ApiKey
    _model: ModelName
    _connect_timeout: int
    _read_timeout: int

    def __init__(self, api_key: ApiKey, model: ModelName, timeout: int = 120, connect_timeout: int = 10) -> None:

        if model not in self.get_available_models():
            raise ValueError(f"Model {model} is not available for {self.id} LMClient")

        if self.api_key_required() and not api_key:
            raise ValueError(f"API key is required for {self.id} LMClient")

        if timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout}")
        if connect_timeout <= 0:
            raise ValueError(f"Connect timeout must be positive, got {connect_timeout}")
        if timeout <= connect_timeout:
            raise ValueError(f"Total timeout ({timeout}) must be greater than connect timeout ({connect_timeout})")

        self._api_key = api_key
        self._model = model
        self._connect_timeout = connect_timeout
        self._read_timeout = timeout - connect_timeout
        self.logger = logging.getLogger(__name__)

    @property
    @abstractmethod
    def id(self) -> str:
        """Return the unique identifier for this LM client."""
        pass

    @staticmethod
    def api_key_required() -> bool:
        return True

    @abstractmethod
    def transform(self, prompt: str, progress_callback: Callable[[ProgressData], None] | None = None) -> LmResponse:
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

    @staticmethod
    @override
    def api_key_required() -> bool:
        return False

    @override
    def transform(self, prompt: str, progress_callback: Callable[[ProgressData], None] | None = None) -> LmResponse:

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
    def transform(self, prompt: str, progress_callback: Callable[[ProgressData], None] | None = None) -> LmResponse:
        """Transform notes using OpenAI API."""
        if not self._api_key or not self._api_key.strip():
            raise ValueError("API key is required for OpenAILMClient")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        data = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
        }

        try:
            result = make_api_request_json(
                url=url,
                method="POST",
                headers=headers,
                json_data=data,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                progress_callback=progress_callback,
            )

            # Extract text from response
            try:
                choices = result.get("choices")
                if not choices or not isinstance(choices, list) or len(choices) == 0:
                    raise KeyError("Missing or empty 'choices' in result")
                choice = choices[0]
                message = choice.get("message")
                if not message or not isinstance(message, dict):
                    raise KeyError("Missing or invalid 'message' in choice")
                text = message.get("content")
                if text is None:
                    raise KeyError("Missing 'content' in message")
                return LmResponse(text)
            except (KeyError, IndexError, TypeError) as e:
                self.logger.error(f"Error parsing OpenAI response: {e}")
                return LmResponse("", f"Error parsing AI response: {e}", e)

        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else str(e)
            self.logger.error(f"OpenAI HTTP Error {e.response.status_code if e.response else 'unknown'}: {error_body}")
            status_code = e.response.status_code if e.response else 'unknown'
            return LmResponse("", f"API Error {status_code}: {error_body}", e)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"OpenAI Network Error: {e}")
            return LmResponse("", f"Network Error: {e}", e)
        except Exception as e:
            self.logger.error(f"OpenAI Unexpected error: {e}")
            return LmResponse("", f"Error: {e!s}", e)

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            # GPT-5 family
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-5-chat",
            "gpt-5.1",
            "gpt-5.1-chat",
            # GPT-4o family (still supported, but older)
            "gpt-4o",
            "gpt-4o-mini",
            "chatgpt-4o-latest",
            # Reasoning models
            "o3-mini",
            "o3-pro",
            "o1",
            "o1-mini",
        ]


class ClaudeLMClient(LMClient):

    @property
    @override
    def id(self) -> str:
        return "claude"

    @override
    def transform(self, prompt: str, progress_callback: Callable[[ProgressData], None] | None = None) -> LmResponse:
        """Transform notes using Claude API."""
        if not self._api_key or not self._api_key.strip():
            raise ValueError("API key is required for ClaudeLMClient")

        url = "https://api.anthropic.com/v1/messages"

        data = {
            "model": self._model,
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
            result = make_api_request_json(
                url=url,
                method="POST",
                headers=headers,
                json_data=data,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                progress_callback=progress_callback,
            )

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

        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else str(e)
            self.logger.error(f"Claude HTTP Error {e.response.status_code if e.response else 'unknown'}: {error_body}")
            status_code = e.response.status_code if e.response else 'unknown'
            return LmResponse("", f"API Error {status_code}: {error_body}", e)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Claude Network Error: {e}")
            return LmResponse("", f"Network Error: {e}", e)
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
    def transform(self, prompt: str, progress_callback: Callable[[ProgressData], None] | None = None) -> LmResponse:
        """Transform notes using Gemini API."""
        if not self._api_key or not self._api_key.strip():
            raise ValueError("API key is required for GeminiLMClient")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"

        data = {"contents": [{"parts": [{"text": prompt}]}]}

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        try:
            result = make_api_request_json(
                url=url,
                method="POST",
                headers=headers,
                json_data=data,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                progress_callback=progress_callback,
            )

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

        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else str(e)
            self.logger.error(f"Gemini HTTP Error {e.response.status_code if e.response else 'unknown'}: {error_body}")
            status_code = e.response.status_code if e.response else 'unknown'
            return LmResponse("", f"API Error {status_code}: {error_body}", e)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Gemini Network Error: {e}")
            return LmResponse("", f"Network Error: {e}", e)
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


class DeepSeekLMClient(LMClient):

    @property
    @override
    def id(self) -> str:
        return "deepseek"

    @override
    def transform(self, prompt: str, progress_callback: Callable[[ProgressData], None] | None = None) -> LmResponse:
        """Transform notes using DeepSeek API."""
        if not self._api_key or not self._api_key.strip():
            raise ValueError("API key is required for DeepSeekLMClient")

        url = "https://api.deepseek.com/chat/completions"

        data = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "model": self._model,
            "stream": False,
            "temperature": 1.0,
            "max_tokens": 1000,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            result = make_api_request_json(
                url=url,
                method="POST",
                headers=headers,
                json_data=data,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                progress_callback=progress_callback,
            )

            # Extract text from response
            try:
                choices = result.get("choices")
                if not choices or not isinstance(choices, list) or len(choices) == 0:
                    raise KeyError("Missing or empty 'choices' in result")
                choice = choices[0]
                message = choice.get("message")
                if not message or not isinstance(message, dict):
                    raise KeyError("Missing or invalid 'message' in choice")
                text = message.get("content")
                if text is None:
                    raise KeyError("Missing 'content' in message")
                return LmResponse(text)
            except (KeyError, IndexError, TypeError) as e:
                self.logger.error(f"Error parsing DeepSeek response: {e}")
                return LmResponse("", f"Error parsing AI response: {e}", e)

        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else str(e)
            self.logger.error(f"DeepSeek HTTP Error {e.response.status_code if e.response else 'unknown'}: {error_body}")
            status_code = e.response.status_code if e.response else 'unknown'
            return LmResponse("", f"API Error {status_code}: {error_body}", e)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"DeepSeek Network Error: {e}")
            return LmResponse("", f"Network Error: {e}", e)
        except Exception as e:
            self.logger.error(f"DeepSeek Unexpected error: {e}")
            return LmResponse("", f"Error: {e!s}", e)

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "deepseek-chat",
        ]



LM_CLIENTS = {
    "dummy": DummyLMClient,
    "openai": OpenAILMClient,
    "claude": ClaudeLMClient,
    "gemini": GeminiLMClient,
    "deepseek": DeepSeekLMClient,
}

def get_lm_client_class(name: str) -> Optional[type[LMClient]]:
    """Return the LM client class (type) for the given client name."""
    if name not in LM_CLIENTS:
        return None
    cls_name = LM_CLIENTS[name].__name__
    cls = globals().get(cls_name)
    return cls
