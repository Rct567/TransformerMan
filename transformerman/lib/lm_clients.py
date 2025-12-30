"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, NewType, Optional

import requests

from .field_updates import FieldUpdates
from .http_utils import LmProgressData, LmRequestStage, make_api_request_json
from .utilities import override
from .xml_parser import notes_from_xml

ApiKey = NewType("ApiKey", str)
ModelName = NewType("ModelName", str)


class LmResponse:
    """Response from a language model containing the text response and parsed notes."""

    def __init__(
        self, content: str, error: str | None = None, exception: Exception | None = None, is_canceled: bool = False
    ) -> None:
        self.content = content
        self.error = error
        self.exception = exception
        self.is_canceled = is_canceled

    def get_notes_from_xml(self) -> FieldUpdates:
        """Parse XML response and extract field updates by note ID."""
        if self.error is not None or self.exception is not None:
            return FieldUpdates()
        return notes_from_xml(self.content)

    def __bool__(self) -> bool:
        return len(self.content) > 0 or self.error is not None or self.exception is not None


class LMClient(ABC):
    """Abstract base class for language model clients."""

    id: str
    name: str

    logger: logging.Logger
    _api_key: ApiKey
    _model: ModelName
    _connect_timeout: int
    _read_timeout: int
    _custom_settings: dict[str, str]

    def __init__(
        self,
        api_key: ApiKey,
        model: ModelName,
        timeout: int = 120,
        connect_timeout: int = 10,
        custom_settings: dict[str, str] | None = None,
    ) -> None:
        if self.get_available_models() and model not in self.get_available_models():
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
        self._custom_settings = custom_settings or {}
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def api_key_required() -> bool:
        return True

    def transform(
        self,
        prompt: str,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LmResponse:
        """Generic transform implementation for network-based clients.

        Args:
            prompt: The prompt to send to the LM.
            progress_callback: Optional callback for progress reporting.
            should_cancel: Optional callback to check if operation should be canceled.

        Returns:
            An LmResponse object containing the content, error, or cancellation status.
        """
        if self.api_key_required() and (not self._api_key or not self._api_key.strip()):
            raise ValueError(f"API key is required for {self.id} LMClient")

        url = self._get_url()
        headers = self._get_headers()
        data = self._get_request_data(prompt)

        try:
            json_response, is_cancelled = make_api_request_json(
                url=url,
                method="POST",
                headers=headers,
                json_data=data,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                progress_callback=progress_callback,
                stream_chunk_parser=self._get_stream_chunk_parser(),
                should_cancel=should_cancel,
            )

            if is_cancelled:
                return LmResponse("", is_canceled=True)

            if json_response is None:
                return LmResponse("", error="Empty response from API", is_canceled=False)

            text_val = json_response.get("content")
            if text_val is not None and isinstance(text_val, str):
                return LmResponse(text_val)

            # Fallback for non-streaming or different response format
            text = self._extract_text_from_non_stream_json(json_response)
            if not text:
                raise KeyError(f"Missing 'content' or vendor-specific fields in {self.id} response")

            return LmResponse(text)

        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else str(e)
            self.logger.error(f"{self.id} HTTP Error {e.response.status_code if e.response else 'unknown'}: {error_body}")
            status_code = e.response.status_code if e.response else "unknown"
            return LmResponse("", f"API Error {status_code}: {error_body}", e)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"{self.id} Network Error: {e}")
            return LmResponse("", f"Network Error: {e}", e)
        except Exception as e:
            self.logger.error(f"{self.id} Unexpected error: {e}")
            return LmResponse("", f"Error: {e!s}", e)

    def get_model(self) -> str:
        """Return the current model name."""
        if "model" in self.custom_settings():
            custom_setting_model = self._custom_settings.get("model", "").strip()
            if custom_setting_model:
                return custom_setting_model

        return self._model

    @abstractmethod
    def _get_url(self) -> str:
        """Return the URL for the API request."""
        pass

    @abstractmethod
    def _get_headers(self) -> dict[str, str]:
        """Return the headers for the API request."""
        pass

    @abstractmethod
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        """Return the JSON data for the API request."""
        pass

    @abstractmethod
    def _extract_text_from_non_stream_json(self, result: dict[str, Any]) -> str:
        """Extract text from a non-streaming JSON response."""
        pass

    @abstractmethod
    def _get_stream_chunk_parser(self) -> Callable[[dict[str, Any]], Optional[str]]:
        """Return a function that extracts text from a stream chunk JSON."""
        pass

    @staticmethod
    @abstractmethod
    def get_available_models() -> list[str]:
        pass

    @staticmethod
    def custom_settings() -> list[str]:
        """Return list of custom setting names for this client."""
        return []

    @staticmethod
    def validate_custom_settings(settings: dict[str, str]) -> tuple[bool, str]:
        """Validate custom settings. Returns (is_valid, error_message)."""
        return True, ""


class DummyLMClient(LMClient):
    """Dummy LM client that returns mock responses for testing."""

    id = "dummy"
    name = "Dummy"

    @staticmethod
    @override
    def api_key_required() -> bool:
        return False

    @override
    def transform(
        self,
        prompt: str,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LmResponse:
        """Dummy transform implementation for testing.

        Args:
            prompt: The prompt to send to the LM.
            progress_callback: Optional callback for progress reporting.
            should_cancel: Optional callback to check if operation should be canceled.

        Returns:
            An LmResponse object containing the content, error, or cancellation status.
        """
        # Extract note IDs and field names from the prompt
        # This is a simple implementation that looks for empty fields

        # Report sending stage
        if progress_callback:
            progress_callback(LmProgressData.in_sending_state())

        if self.get_model() == "lorem_ipsum_network":
            if random.random() < 0.5:
                time.sleep(random.uniform(0.1, 8.0))
            else:
                time.sleep(random.uniform(8.0, 10.0))

        # Find all note blocks
        note_pattern = r'<note nid="(\d+)"[^>]*>(.*?)</note>'
        notes = re.findall(note_pattern, prompt, re.DOTALL)

        if not notes:
            return LmResponse("<notes></notes>")

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
                    # Fill empty field with Lorem ipsum content
                    lorem_content = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
                    response_parts.append(f'    <field name="{field_name}">{lorem_content}</field>')

            response_parts.append("  </note>")

        response_parts.append("</notes>")

        full_text = "\n".join(response_parts)

        # Simulate streaming if progress_callback is provided
        if progress_callback:
            start_time = time.time()
            # Split into small chunks to simulate real streaming
            chunk_size = 200
            for i in range(0, len(full_text), chunk_size):
                chunk = full_text[i : i + chunk_size]
                elapsed = time.time() - start_time
                progress_callback(
                    LmProgressData(
                        stage=LmRequestStage.RECEIVING,
                        text_chunk=chunk,
                        total_chars=i + len(chunk),
                        total_bytes=i + len(chunk),  # Mock bytes same as chars
                        elapsed=elapsed,
                    )
                )
                if self.get_model() == "lorem_ipsum_network":
                    time.sleep(random.uniform(0.01, 0.2))  # Delay to simulate network
                else:
                    time.sleep(0.01)  # Small delay for local processing

                if should_cancel and should_cancel():
                    return LmResponse("", is_canceled=True)

        return LmResponse(full_text)

    @override
    def _get_url(self) -> str:
        return ""

    @override
    def _get_headers(self) -> dict[str, str]:
        return {}

    @override
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        return {}

    @override
    def _extract_text_from_non_stream_json(self, result: dict[str, Any]) -> str:
        return ""

    @override
    def _get_stream_chunk_parser(self) -> Callable[[dict[str, Any]], Optional[str]]:
        return lambda data: ""

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return ["lorem_ipsum", "lorem_ipsum_network"]


class OpenAiCompatibleLMClient(LMClient):
    """Base class for OpenAI-compatible API clients."""

    @override
    def _extract_text_from_non_stream_json(self, result: dict[str, Any]) -> str:
        choices = result.get("choices")
        if isinstance(choices, list) and len(choices) > 0:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    return str(message.get("content", ""))
        return ""

    @override
    def _get_stream_chunk_parser(self) -> Callable[[dict[str, Any]], Optional[str]]:
        def parser(data: dict[str, Any]) -> Optional[str]:
            if "choices" in data and len(data["choices"]) > 0:
                delta = data["choices"][0].get("delta", {})
                return delta.get("content")
            return None

        return parser


class OpenAILMClient(OpenAiCompatibleLMClient):
    id = "openai"
    name = "OpenAI"

    @override
    def _get_url(self) -> str:
        url = self._custom_settings.get("end_point", "https://api.openai.com/v1/chat/completions")
        if url.endswith("/v1"):
            url += "/chat/completions"
        return url

    @override
    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        organization_id = self._custom_settings.get("organization_id")
        if organization_id:
            headers["OpenAI-Organization"] = organization_id.strip()
        return headers

    @override
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.get_model(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "stream": True,
        }

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

    @staticmethod
    @override
    def custom_settings() -> list[str]:
        """Return list of custom setting names for OpenAI client."""
        return ["organization_id"]

    @staticmethod
    @override
    def validate_custom_settings(settings: dict[str, str]) -> tuple[bool, str]:
        """Validate custom settings for OpenAI client."""
        # Validate end_point if provided
        if "end_point" in settings:
            end_point = settings["end_point"].strip()
            if end_point and not end_point.startswith(("http://", "https://")):
                return False, "end_point must be a valid URL starting with http:// or https://"

        if "model" in settings:
            model = settings["model"].strip()
            if model and not re.match(r"^[a-zA-Z0-9\-_\.\/]+$", model):
                return False, "model must contain only alphanumeric characters, hyphens, underscores, and periods"

        # Validate organization_id if provided
        if "organization_id" in settings:
            org_id = settings["organization_id"].strip()
            if org_id and not org_id.replace("-", "").replace("_", "").isalnum():
                return False, "organization_id must contain only alphanumeric characters, hyphens, and underscores"

        return True, ""


class CustomOpenAi(OpenAILMClient):
    id = "custom_openai_endpoint"
    name = "Custom OpenAI"

    @staticmethod
    @override
    def custom_settings() -> list[str]:
        """Return list of custom setting names for OpenAI client."""
        return ["end_point", "model", "organization_id"]

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return []


class LmStudio(OpenAILMClient):
    id = "lm-studio"
    name = "LM Studio"

    @override
    def __init__(
        self,
        api_key: ApiKey,
        model: ModelName,
        timeout: int = 120,
        connect_timeout: int = 10,
        custom_settings: dict[str, str] | None = None,
    ) -> None:
        if custom_settings:
            port = custom_settings.get("port", "").strip()
            if not port or not port.isdigit():
                port = "1234"
            custom_settings["end_point"] = "http://127.0.0.1:{}/v1".format(port)
        self._api_key = ApiKey("lm-studio")
        super().__init__(api_key, model, timeout, connect_timeout, custom_settings)

    @override
    @staticmethod
    def api_key_required() -> bool:
        return False

    @staticmethod
    @override
    def custom_settings() -> list[str]:
        """Return list of custom setting names for OpenAI client."""
        return ["model", "port"]

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return []


class GroqLMClient(OpenAILMClient):
    id = "groq"
    name = "Groq"

    @override
    def __init__(
        self,
        api_key: ApiKey,
        model: ModelName,
        timeout: int = 120,
        connect_timeout: int = 10,
        custom_settings: dict[str, str] | None = None,
    ) -> None:
        if not custom_settings:
            custom_settings = {}
        custom_settings["end_point"] = "https://api.groq.com/openai/v1/chat/completions"
        super().__init__(api_key, model, timeout, connect_timeout, custom_settings)

    @staticmethod
    @override
    def custom_settings() -> list[str]:
        """Return list of custom setting names for OpenAI client."""
        return ["model", "organization_id"]

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return []


class ClaudeLMClient(LMClient):
    id = "claude"
    name = "Claude"

    @override
    def _get_url(self) -> str:
        return "https://api.anthropic.com/v1/messages"

    @override
    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

    @override
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": 4096,
        }

    @override
    def _extract_text_from_non_stream_json(self, result: dict[str, Any]) -> str:
        content = result.get("content")
        if isinstance(content, list) and len(content) > 0:
            item = content[0]
            if isinstance(item, dict):
                return str(item.get("text", ""))
        return ""

    @override
    def _get_stream_chunk_parser(self) -> Callable[[dict[str, Any]], Optional[str]]:
        def parser(data: dict[str, Any]) -> Optional[str]:
            if "delta" in data:
                return data["delta"].get("text")
            return None

        return parser

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "claude-sonnet-4-5",  # Latest Sonnet 4.5 (balanced, recommended starting point)
            "claude-opus-4-5",  # Latest Opus 4.5 (most capable)
            "claude-haiku-4-5",  # Latest Haiku 4.5 (fastest/cheapest)
        ]


class GeminiLMClient(LMClient):
    id = "gemini"
    name = "Gemini"

    @override
    def _get_url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:streamGenerateContent?alt=sse"

    @override
    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

    @override
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        return {"contents": [{"parts": [{"text": prompt}]}]}

    @override
    def _extract_text_from_non_stream_json(self, result: dict[str, Any]) -> str:
        candidates = result.get("candidates")
        if isinstance(candidates, list) and len(candidates) > 0:
            candidate = candidates[0]
            if isinstance(candidate, dict):
                content = candidate.get("content")
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list) and parts:
                        part = parts[0]
                        if isinstance(part, dict):
                            return str(part.get("text", ""))
        return ""

    @override
    def _get_stream_chunk_parser(self) -> Callable[[dict[str, Any]], Optional[str]]:
        def parser(data: dict[str, Any]) -> Optional[str]:
            if "candidates" in data:
                candidates = data["candidates"]
                if candidates and isinstance(candidates, list):
                    candidate = candidates[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    if parts and isinstance(parts, list):
                        return parts[0].get("text")
            return None

        return parser

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return [
            "gemini-2.5-flash",  # Stable Gemini 2.5 Flash (fast, balanced, recommended for most apps)
            "gemini-2.5-pro",  # Stable Gemini 2.5 Pro (advanced reasoning, complex tasks)
            "gemini-2.5-flash-lite",  # Stable lite variant (cheapest/fastest for high-volume)
            "gemini-flash-latest",  # Alias for the absolute latest Flash experimental (auto-updates)
        ]


class DeepSeekLMClient(OpenAiCompatibleLMClient):
    id = "deepseek"
    name = "DeepSeek"

    @override
    def _get_url(self) -> str:
        return "https://api.deepseek.com/chat/completions"

    @override
    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    @override
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        return {
            "messages": [{"role": "user", "content": prompt}],
            "model": self._model,
            "stream": True,
            "temperature": 1.0,
        }

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return ["deepseek-chat", "deepseek-reasoner"]


class GrokLMClient(OpenAiCompatibleLMClient):
    id = "grok"
    name = "Grok"

    @override
    def _get_url(self) -> str:
        return "https://api.x.ai/v1/chat/completions"

    @override
    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    @override
    def _get_request_data(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }

    @staticmethod
    @override
    def get_available_models() -> list[str]:
        return ["grok-4-1-fast", "grok-4-1-fast-reasoning", "grok-4", "grok-4-fast-non-reasoning", "grok-3"]


LM_CLIENTS_CLASSES = [
    DummyLMClient,
    OpenAILMClient,
    ClaudeLMClient,
    GeminiLMClient,
    DeepSeekLMClient,
    GroqLMClient,
    GrokLMClient,
    LmStudio,
    CustomOpenAi,
]

assert len(LM_CLIENTS_CLASSES) == len(set(client.id for client in LM_CLIENTS_CLASSES)), "Duplicate LM client IDs detected"

LM_CLIENTS = {client.id: client for client in LM_CLIENTS_CLASSES}


def get_lm_client_class(name: str) -> Optional[type[LMClient]]:
    """Return the LM client class (type) for the given client name."""
    if name not in LM_CLIENTS:
        return None
    return LM_CLIENTS[name]
