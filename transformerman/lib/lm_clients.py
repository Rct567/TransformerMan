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
from typing import Any, Callable, NamedTuple, NewType, Optional

import requests

from .field_updates import FieldUpdates
from .http_utils import LmProgressData, LmRequestStage, make_api_request_json
from .utilities import get_lorem_sentences_generator, override
from .xml_parser import notes_from_xml

ApiKey = NewType("ApiKey", str)
ModelName = NewType("ModelName", str)


class AvailableModels(NamedTuple):
    """Result of fetching available models from an API."""

    models: list[ModelName]
    error: str | None = None


class LmResponse:
    """Response from a language model containing the text response and parsed notes."""

    def __init__(self, content: str, error: str | None = None, exception: Exception | None = None, is_canceled: bool = False) -> None:
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
    _model: ModelName | None
    _connect_timeout: int
    _read_timeout: int
    _custom_settings: dict[str, str]

    def __init__(
        self,
        api_key: ApiKey,
        model: ModelName | None = None,
        timeout: int = 120,
        connect_timeout: int = 10,
        custom_settings: dict[str, str] | None = None,
    ) -> None:
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

    def process_prompt(
        self,
        prompt: str,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LmResponse:
        """Process prompt using the LM client.

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

        return str(self._model)

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
    def get_recommended_models() -> list[ModelName]:
        """Return a curated list of recommended models for this client."""
        pass

    @staticmethod
    def supports_fetching_available_models() -> bool:
        """Return True if this client supports fetching available models from an API."""
        return True

    @abstractmethod
    def fetch_available_models(self) -> AvailableModels:
        """Fetch available models from the API."""
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
    def process_prompt(
        self,
        prompt: str,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LmResponse:
        """Dummy process_prompt implementation for testing."""
        # Report sending stage
        if progress_callback:
            progress_callback(LmProgressData.in_sending_state())

        if self.get_model() == "lorem_ipsum_network":
            if random.random() < 0.5:
                time.sleep(random.uniform(0.1, 8.0))
            else:
                time.sleep(random.uniform(8.0, 10.0))

        # Detect prompt type
        if "Please generate " in prompt:
            full_text = self._handle_generation_prompt(prompt)
        elif "Please fill " in prompt and "empty fields" in prompt:
            full_text = self._handle_transform_prompt(prompt)
        else:
            raise ValueError(f"Unknown prompt type: {prompt}")

        return self._simulate_streaming(full_text, progress_callback, should_cancel)

    def _handle_transform_prompt(self, prompt: str) -> str:
        """Handle prompts for transforming existing notes."""
        # Find all note blocks
        note_pattern = r'<note nid="(\d+)"[^>]*>(.*?)</note>'
        notes = re.findall(note_pattern, prompt, re.DOTALL)

        if not notes:
            return "<notes></notes>"

        # Extract model name
        model_match = re.search(r'<notes model="([^"]+)">', prompt)
        model_name = model_match.group(1) if model_match else "Unknown"

        # Build response
        response_parts = [f'<notes model="{model_name}">']

        generate_lorem_sentence = get_lorem_sentences_generator(1, (6, 10))

        for nid, note_content in notes:
            # Extract deck name
            deck_match = re.search(r'deck="([^"]+)"', note_content)
            deck_name = deck_match.group(1) if deck_match else ""

            # Find empty fields
            field_pattern = r'<field name="([^"]+)">([^<]*)</field>'
            fields = re.findall(field_pattern, note_content)
            field_updates: dict[str, str] = {}

            for field_name, field_value in fields:
                if field_value.strip():
                    continue

                field_updates[field_name] = generate_lorem_sentence()

            if field_updates:
                response_parts.append(f'  <note nid="{nid}" deck="{deck_name}">')
                for field_name, field_value in field_updates.items():
                    response_parts.append(f'    <field name="{field_name}">{field_value}</field>')
                response_parts.append("  </note>")

        response_parts.append("</notes>")
        return "\n".join(response_parts)

    def _handle_generation_prompt(self, prompt: str) -> str:
        """Handle prompts for generating new notes."""
        # Extract metadata
        model_match = re.search(r"Target Note Type: (.*)", prompt)
        deck_match = re.search(r"Target Deck: (.*)", prompt)
        fields_match = re.search(r"Available Fields: (.*)", prompt)
        count_match = re.search(r"Target Number of Notes: (\d+)", prompt)

        model_name = model_match.group(1).strip() if model_match else "Unknown"
        deck_name = deck_match.group(1).strip() if deck_match else "Default"
        field_names = [f.strip() for f in fields_match.group(1).split(",")] if fields_match else []
        target_count = int(count_match.group(1)) if count_match else 1

        # Build response
        response_parts = [f'<notes model="{model_name}" deck="{deck_name}">']
        generate_lorem_sentence = get_lorem_sentences_generator(1, (6, 10))

        for _ in range(target_count):
            response_parts.append("  <note>")
            for field_name in field_names:
                lorem_content = generate_lorem_sentence()
                response_parts.append(f'    <field name="{field_name}">{lorem_content}</field>')
            response_parts.append("  </note>")

        response_parts.append("</notes>")
        return "\n".join(response_parts)

    def _simulate_streaming(
        self,
        full_text: str,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LmResponse:
        """Simulate streaming of the response text."""
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
    def get_recommended_models() -> list[ModelName]:
        return [ModelName("lorem_ipsum"), ModelName("lorem_ipsum_network")]

    @staticmethod
    @override
    def supports_fetching_available_models() -> bool:
        return False

    @override
    def fetch_available_models(self) -> AvailableModels:
        """Dummy client doesn't support fetching models via API."""
        return AvailableModels(models=[], error="Fetching models is not supported for this client")


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

    @override
    def fetch_available_models(self) -> AvailableModels:
        """Fetch available models from OpenAI /v1/models endpoint."""
        # Build models URL
        base_url = self._get_url().replace("/chat/completions", "/models")

        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._custom_settings and "organization_id" in self._custom_settings:
            org_id = self._custom_settings["organization_id"].strip()
            if org_id:
                headers["OpenAI-Organization"] = org_id

        try:
            response = requests.get(base_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            models = [ModelName(m["id"]) for m in data.get("data", [])]
            return AvailableModels(models=models)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            return AvailableModels(models=[], error=f"API Error {status}")
        except Exception as e:
            return AvailableModels(models=[], error=str(e))


class OpenAILMClient(OpenAiCompatibleLMClient):
    id = "openai"
    name = "OpenAI"

    @override
    def _get_url(self) -> str:
        url = self._custom_settings.get("end_point", "https://api.openai.com/v1/chat/completions")
        if url.endswith("/v1"):
            url += "/chat/completions"
        return url

    @staticmethod
    @override
    def get_recommended_models() -> list[ModelName]:
        return [
            # GPT-5 family
            ModelName("gpt-5"),
            ModelName("gpt-5-mini"),
            ModelName("gpt-5-nano"),
            ModelName("gpt-5-chat"),
            ModelName("gpt-5.1"),
            ModelName("gpt-5.1-chat"),
            # GPT-4o family (still supported, but older)
            ModelName("gpt-4o"),
            ModelName("gpt-4o-mini"),
            ModelName("chatgpt-4o-latest"),
            # Reasoning models
            ModelName("o3-mini"),
            ModelName("o3-pro"),
            ModelName("o1"),
            ModelName("o1-mini"),
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


class CustomOpenAi(OpenAiCompatibleLMClient):
    id = "custom_openai_endpoint"
    name = "Custom OpenAI"

    @override
    def _get_url(self) -> str:
        url = self._custom_settings.get("end_point", "https://api.openai.com/v1/chat/completions")
        if url.endswith("/v1"):
            url += "/chat/completions"
        return url

    @staticmethod
    @override
    def custom_settings() -> list[str]:
        """Return list of custom setting names for OpenAI client."""
        return ["end_point", "organization_id"]

    @staticmethod
    @override
    def get_recommended_models() -> list[ModelName]:
        return []

    @staticmethod
    @override
    def validate_custom_settings(settings: dict[str, str]) -> tuple[bool, str]:
        """Validate custom settings for Custom OpenAI client."""
        if "end_point" not in settings or not settings["end_point"].strip():
            return False, "end_point is required for Custom OpenAI client"
        return super(CustomOpenAi, CustomOpenAi).validate_custom_settings(settings)


class LmStudio(OpenAiCompatibleLMClient):
    id = "lm-studio"
    name = "LM Studio"

    @override
    def _get_url(self) -> str:
        url = self._construct_endpoint(self._custom_settings)
        if url.endswith("/v1"):
            url += "/chat/completions"
        return url

    @override
    def __init__(
        self,
        api_key: ApiKey,
        model: ModelName | None = None,
        timeout: int = 120,
        connect_timeout: int = 10,
        custom_settings: dict[str, str] | None = None,
    ) -> None:
        self._api_key = ApiKey("lm-studio")
        super().__init__(api_key, model, timeout, connect_timeout, custom_settings)

    @staticmethod
    def _construct_endpoint(custom_settings: dict[str, str] | None) -> str:
        """Construct API endpoint from port setting."""
        port = "1234"
        if custom_settings:
            p = custom_settings.get("port", "").strip()
            if p and p.isdigit():
                port = p
        return f"http://127.0.0.1:{port}/v1"

    @override
    @staticmethod
    def api_key_required() -> bool:
        return False

    @staticmethod
    @override
    def custom_settings() -> list[str]:
        """Return list of custom setting names for OpenAI client."""
        return ["port"]

    @staticmethod
    @override
    def get_recommended_models() -> list[ModelName]:
        return []


class GroqLMClient(OpenAiCompatibleLMClient):
    id = "groq"
    name = "Groq"

    @override
    def _get_url(self) -> str:
        return "https://api.groq.com/openai/v1/chat/completions"

    @staticmethod
    @override
    def get_recommended_models() -> list[ModelName]:
        return [
            ModelName("openai/gpt-oss-120b"),
        ]


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
    def get_recommended_models() -> list[ModelName]:
        return [
            ModelName("claude-sonnet-4-5"),  # Latest Sonnet 4.5 (balanced, recommended starting point)
            ModelName("claude-opus-4-5"),  # Latest Opus 4.5 (most capable)
            ModelName("claude-haiku-4-5"),  # Latest Haiku 4.5 (fastest/cheapest)
        ]

    @override
    def fetch_available_models(self) -> AvailableModels:
        """Fetch available models from Anthropic /v1/models endpoint."""
        try:
            response = requests.get(
                "https://api.anthropic.com/v1/models", headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}, timeout=10
            )
            response.raise_for_status()
            data = response.json()
            models = [ModelName(m["id"]) for m in data.get("data", [])]
            return AvailableModels(models=models)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            return AvailableModels(models=[], error=f"API Error {status}")
        except Exception as e:
            return AvailableModels(models=[], error=str(e))


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
    def get_recommended_models() -> list[ModelName]:
        return [
            ModelName("gemini-flash-latest"),  # Alias for the latest Flash experimental (auto-updates)
            ModelName("gemini-2.5-flash"),  # Stable Gemini 2.5 Flash (fast, balanced, recommended for most apps)
            ModelName("gemini-2.5-pro"),  # Stable Gemini 2.5 Pro (advanced reasoning, complex tasks)
            ModelName("gemini-2.5-flash-lite"),  # Stable lite variant (cheapest/fastest for high-volume)
            ModelName("gemini-3-flash-preview"),
        ]

    @override
    def fetch_available_models(self) -> AvailableModels:
        """Fetch available models from Google Gemini /v1beta/models endpoint."""
        try:
            response = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={self._api_key}", timeout=10)
            response.raise_for_status()
            data = response.json()
            # Extract model name from "models/gemini-..." format
            models = [ModelName(m["name"].replace("models/", "")) for m in data.get("models", [])]
            return AvailableModels(models=models)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            return AvailableModels(models=[], error=f"API Error {status}")
        except Exception as e:
            return AvailableModels(models=[], error=str(e))


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
    def get_recommended_models() -> list[ModelName]:
        return [ModelName("deepseek-chat"), ModelName("deepseek-reasoner")]


class GrokLMClient(OpenAiCompatibleLMClient):
    id = "grok"
    name = "Grok (x.ai)"

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
    def get_recommended_models() -> list[ModelName]:
        return [
            ModelName("grok-4-1-fast"),
            ModelName("grok-4-1-fast-reasoning"),
            ModelName("grok-4"),
            ModelName("grok-4-fast-non-reasoning"),
            ModelName("grok-3"),
        ]


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
