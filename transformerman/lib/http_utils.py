"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.

HTTP utilities for making API requests with progress callbacks.
"""

from __future__ import annotations

from enum import Enum, auto
import json
import time
from typing import TYPE_CHECKING, Any, Callable, NamedTuple, Optional

import requests

if TYPE_CHECKING:
    from transformerman.lib.utilities import JSON_TYPE


class LmRequestStage(Enum):
    """Stage of the LM request."""

    SENDING = auto()
    RECEIVING = auto()


class LmProgressData(NamedTuple):
    """Data passed to progress callbacks during LLM streaming."""

    stage: LmRequestStage
    text_chunk: str  # Current text chunk (empty string for non-streaming updates)
    total_chars: int  # Total characters received so far
    elapsed: float  # Time elapsed since request started
    content_length: Optional[int] = None  # Total expected bytes (if known)


def make_api_request(
    url: str,
    method: str = "POST",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict[str, Any]] = None,
    json_data: Optional[dict[str, JSON_TYPE]] = None,
    connect_timeout: int = 10,
    read_timeout: int = 110,
    progress_callback: Optional[Callable[[LmProgressData], None]] = None,
    chunk_size: int = 8192,
) -> bytes:
    """
    Make an HTTP request with progress callback support.
    For LLM APIs, supports Server-Sent Events (SSE) streaming.

    Args:
        url: The URL to request
        method: HTTP method (GET, POST, etc.)
        headers: HTTP headers to include
        data: Form data to send (for form-encoded POST)
        json_data: JSON data to send (for JSON POST)
        connect_timeout: Connection timeout in seconds
        read_timeout: Read timeout in seconds
        progress_callback: Function called with LmProgressData(text_chunk, total_chars, elapsed)
        chunk_size: Size of chunks to read at a time for streaming

    Returns:
        The response content as bytes

    Raises:
        requests.exceptions.Timeout: If the request times out
        requests.exceptions.HTTPError: If the HTTP response status code is not 2xx
        requests.exceptions.RequestException: For other request-related errors
    """
    if headers is None:
        headers = {}

    # Report sending stage
    if progress_callback:
        progress_callback(LmProgressData(stage=LmRequestStage.SENDING, text_chunk="", total_chars=0, elapsed=0.0, content_length=None))

    # Make the request with parameters based on what's provided
    if json_data is not None:
        response = requests.request(method, url, headers=headers, json=json_data, timeout=(connect_timeout, read_timeout), stream=progress_callback is not None)
    elif data is not None:
        response = requests.request(method, url, headers=headers, data=data, timeout=(connect_timeout, read_timeout), stream=progress_callback is not None)
    else:
        response = requests.request(method, url, headers=headers, timeout=(connect_timeout, read_timeout), stream=progress_callback is not None)
    response.raise_for_status()  # Raise exception for bad status codes

    # Check if this is likely an SSE stream (text/event-stream or streaming LLM API)
    content_type = response.headers.get("Content-Type", "").lower()
    is_sse_stream = "text/event-stream" in content_type or (json_data is not None and json_data.get("stream") is True)

    if is_sse_stream:
        # Handle SSE streaming for LLM APIs
        return _handle_sse_stream(response, progress_callback)

    # If no progress callback and not SSE, read the entire response
    if progress_callback is None:
        return response.content

    # Handle regular byte streaming (for backward compatibility, though not used for LLMs)
    return _handle_byte_stream(response, progress_callback, chunk_size)


def _handle_sse_stream(response: requests.Response, progress_callback: Optional[Callable[[LmProgressData], None]]) -> bytes:
    """
    Handle Server-Sent Events (SSE) streaming for LLM APIs.
    Also handles non-SSE JSON responses as fallback.

    Args:
        response: The streaming HTTP response
        progress_callback: Function to call with progress updates

    Returns:
        A JSON response matching the expected API format
    """
    full_text = ""
    start_time = time.time()
    url = response.url

    # First, collect all response content
    response_content = b""
    downloaded = 0
    content_length_header = response.headers.get("Content-Length")
    content_length = int(content_length_header) if content_length_header is not None and content_length_header.isdigit() else None

    for chunk in response.iter_content(chunk_size=8192):
        if chunk:
            response_content += chunk
            downloaded += len(chunk)

            # Report download progress
            if progress_callback:
                elapsed = time.time() - start_time
                progress_data = LmProgressData(stage=LmRequestStage.RECEIVING, text_chunk="", total_chars=downloaded, elapsed=elapsed, content_length=content_length)
                progress_callback(progress_data)

    response_text = response_content.decode("utf-8")

    # Check if it's SSE format (contains "data: " lines)
    if "data: " in response_text:
        # Parse as SSE
        lines = response_text.split("\n")
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith(":"):
                continue

            if line.startswith("data: "):
                data_str = line[6:]  # Remove "data: " prefix
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                    chunk_text = _extract_text_from_sse_data(data)

                    if chunk_text:
                        full_text += chunk_text
                        elapsed = time.time() - start_time
                        progress_data = LmProgressData(stage=LmRequestStage.RECEIVING, text_chunk=chunk_text, total_chars=len(full_text), elapsed=elapsed, content_length=content_length)
                        if progress_callback:
                            progress_callback(progress_data)

                except json.JSONDecodeError:
                    continue
    else:
        # Not SSE, try to parse as regular JSON
        try:
            data = json.loads(response_text)

            # Extract text from regular JSON response
            if data.get("choices"):
                # OpenAI/DeepSeek format
                message = data["choices"][0].get("message", {})
                chunk_text = message.get("content", "")
                if chunk_text:
                    full_text = chunk_text
            elif data.get("content"):
                # Anthropic format
                chunk_text = data["content"][0].get("text", "")
                if chunk_text:
                    full_text = chunk_text
            elif data.get("candidates"):
                # Gemini format
                candidate = data["candidates"][0]
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                if parts:
                    chunk_text = parts[0].get("text", "")
                    if chunk_text:
                        full_text = chunk_text

            # Call progress callback with complete text
            if full_text:
                elapsed = time.time() - start_time
                progress_data = LmProgressData(stage=LmRequestStage.RECEIVING, text_chunk=full_text, total_chars=len(full_text), elapsed=elapsed, content_length=content_length)
                if progress_callback:
                    progress_callback(progress_data)

        except json.JSONDecodeError:
            # Return empty JSON to avoid breaking the caller
            pass

    return _construct_final_json(url, full_text)


def _extract_text_from_sse_data(data: dict) -> str:
    """
    Extract text chunk from SSE data based on API format.

    Args:
        data: Parsed JSON data from SSE event

    Returns:
        Extracted text chunk, or empty string if not found
    """
    # OpenAI format:
    if "choices" in data and len(data["choices"]) > 0:
        delta = data["choices"][0].get("delta", {})
        return delta.get("content", "")

    # Anthropic format:
    elif "delta" in data:
        return data["delta"].get("text", "")

    # DeepSeek format (similar to OpenAI):
    elif data.get("choices"):
        choice = data["choices"][0]
        if "delta" in choice:
            return choice["delta"].get("content", "")
        elif "text" in choice:
            return choice.get("text", "")

    # Gemini format:
    elif "candidates" in data:
        candidates = data["candidates"]
        if candidates and isinstance(candidates, list):
            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            if parts and isinstance(parts, list):
                return parts[0].get("text", "")

    # Generic fallback
    for key in ["content", "text", "message"]:
        if key in data:
            if isinstance(data[key], str):
                return data[key]
            elif isinstance(data[key], dict) and "content" in data[key]:
                return data[key]["content"]

    return ""


def _construct_final_json(url: str, full_text: str) -> bytes:
    """
    Construct final JSON response based on API URL.

    Args:
        url: API URL
        full_text: Complete response text

    Returns:
        JSON-encoded bytes
    """
    # Determine API format from URL
    if "openai.com" in url or "api.openai.com" in url:
        result_json = {"choices": [{"message": {"content": full_text}}]}
    elif "anthropic.com" in url or "api.anthropic.com" in url:
        result_json = {"content": [{"text": full_text}]}  # type: ignore[dict-item]
    elif "deepseek.com" in url or "api.deepseek.com" in url:
        result_json = {"choices": [{"message": {"content": full_text}}]}
    elif "generativelanguage.googleapis.com" in url:
        result_json = {"candidates": [{"content": {"parts": [{"text": full_text}]}}]}  # type: ignore[dict-item]
    else:
        # Default to OpenAI format
        result_json = {"choices": [{"message": {"content": full_text}}]}

    return json.dumps(result_json).encode("utf-8")


def _handle_byte_stream(response: requests.Response, progress_callback: Optional[Callable[[LmProgressData], None]], chunk_size: int) -> bytes:
    """
    Handle regular byte streaming (for non-LLM requests or backward compatibility).

    Args:
        response: The streaming HTTP response
        progress_callback: Function to call with progress updates
        chunk_size: Size of chunks to read

    Returns:
        The complete response content as bytes
    """
    content_length_header = response.headers.get("Content-Length")
    content_length = int(content_length_header) if content_length_header is not None and content_length_header.isdigit() else None
    downloaded = 0
    start_time = time.time()
    content_parts = []

    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:  # filter out keep-alive new chunks
            content_parts.append(chunk)
            downloaded += len(chunk)

            # Calculate metrics
            elapsed = time.time() - start_time

            # For byte streaming, we don't have text chunks, so pass empty string
            # But we can show progress based on bytes downloaded
            progress_data = LmProgressData(
                stage=LmRequestStage.RECEIVING,
                text_chunk="",  # No text chunk for byte streaming
                total_chars=downloaded,  # Use bytes as "chars" for compatibility
                elapsed=elapsed,
                content_length=content_length,
            )
            if progress_callback:
                progress_callback(progress_data)

    return b"".join(content_parts)


def make_api_request_json(
    url: str,
    method: str = "POST",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict] = None,
    json_data: Optional[dict] = None,
    connect_timeout: int = 10,
    read_timeout: int = 110,
    progress_callback: Optional[Callable[[LmProgressData], None]] = None,
    chunk_size: int = 8192,
) -> dict[str, Any]:
    """
    Make an HTTP request and parse the response as JSON.

    Args:
        url: The URL to request
        method: HTTP method (GET, POST, etc.)
        headers: HTTP headers to include
        data: Form data to send (for form-encoded POST)
        json_data: JSON data to send (for JSON POST)
        connect_timeout: Connection timeout in seconds
        read_timeout: Read timeout in seconds
        progress_callback: Function called with LmProgressData(text_chunk, total_chars, elapsed)
        chunk_size: Size of chunks to read at a time for streaming

    Returns:
        The parsed JSON response as a dictionary

    Raises:
        requests.exceptions.Timeout: If the request times out
        requests.exceptions.HTTPError: If the HTTP response status code is not 2xx
        requests.exceptions.RequestException: For other request-related errors
        ValueError: If the response is not valid JSON or is not a JSON object (dict)
    """

    content = make_api_request(
        url=url, method=method, headers=headers, data=data, json_data=json_data, connect_timeout=connect_timeout, read_timeout=read_timeout, progress_callback=progress_callback, chunk_size=chunk_size
    )

    content_str = content.decode("utf-8")

    try:
        parsed = json.loads(content_str)
    except json.JSONDecodeError:
        raise

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object (dict), got {type(parsed).__name__}")

    return parsed
