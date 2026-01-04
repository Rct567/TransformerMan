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
    from .utilities import JSON_TYPE


class LmRequestStage(Enum):
    """Stage of the LM request."""

    SENDING = auto()
    RECEIVING = auto()


class LmProgressData(NamedTuple):
    """Data passed to progress callbacks during LLM streaming."""

    stage: LmRequestStage
    text_chunk: str  # Current text chunk (empty string for non-streaming updates)
    total_chars: int  # Total characters of extracted text received so far # noqa: F841
    total_bytes: int  # Total raw bytes received so far (network size)
    elapsed: float  # Time elapsed since request started
    content_length: Optional[int] = None  # Total expected bytes (if known)

    @staticmethod
    def in_sending_state() -> LmProgressData:
        return LmProgressData(
            stage=LmRequestStage.SENDING,
            text_chunk="",
            total_chars=0,
            total_bytes=0,
            elapsed=0.0,
            content_length=None,
        )


def make_api_request(  # noqa: PLR0913
    url: str,
    method: str = "POST",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict[str, Any]] = None,
    json_data: Optional[dict[str, JSON_TYPE]] = None,
    connect_timeout: int = 10,
    read_timeout: int = 110,
    progress_callback: Optional[Callable[[LmProgressData], None]] = None,
    stream_chunk_parser: Optional[Callable[[dict[str, Any]], Optional[str]]] = None,
    chunk_size: int = 8192,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> tuple[bytes | None, bool]:
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
        progress_callback: Function called with LmProgressData
        stream_chunk_parser: Optional function to extract text from SSE JSON data
        chunk_size: Size of chunks to read at a time for streaming
        should_cancel: Optional callback to check if operation should be canceled.

    Returns:
        A tuple of (response_content, is_cancelled). response_content is bytes or None if cancelled.

    Raises:
        requests.exceptions.Timeout: If the request times out
        requests.exceptions.HTTPError: If the HTTP response status code is not 2xx
        requests.exceptions.RequestException: For other request-related errors
    """
    if headers is None:
        headers = {}

    # Report sending stage
    if progress_callback:
        progress_callback(LmProgressData.in_sending_state())

    # Make the request with parameters based on what's provided
    # We use stream=True if we have a progress callback OR if we expect SSE
    timeout = (connect_timeout, read_timeout)
    is_streaming = progress_callback is not None or (json_data is not None and json_data.get("stream") is True)

    with requests.request(
        method,
        url,
        headers=headers,
        json=json_data if json_data is not None else None,
        data=data if data is not None else None,
        timeout=timeout,
        stream=is_streaming,
    ) as response:
        response.raise_for_status()

        # Check if this is an SSE stream
        content_type = response.headers.get("Content-Type", "").lower()
        is_sse_stream = "text/event-stream" in content_type or (json_data is not None and json_data.get("stream") is True)

        if is_sse_stream:
            return _handle_sse_stream(response, progress_callback, stream_chunk_parser, should_cancel)

        # If no progress callback and not SSE, read the entire response
        if progress_callback is None:
            if should_cancel and should_cancel():
                return None, True
            return response.content, False

        # Handle regular byte streaming
        return _handle_byte_stream(response, progress_callback, chunk_size, should_cancel)


def _handle_sse_stream(
    response: requests.Response,
    progress_callback: Optional[Callable[[LmProgressData], None]],
    stream_chunk_parser: Optional[Callable[[dict[str, Any]], Optional[str]]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> tuple[bytes | None, bool]:
    """
    Handle Server-Sent Events (SSE) streaming for LLM APIs in real-time.

    Returns:
        A tuple of (response_content, is_cancelled). response_content is bytes or None if cancelled.
    """
    full_text = ""
    start_time = time.time()

    content_length_header = response.headers.get("Content-Length")
    content_length = int(content_length_header) if content_length_header is not None and content_length_header.isdigit() else None

    downloaded_bytes = 0

    # Force UTF-8 encoding if not specified in headers, as most LM APIs return UTF-8.
    # Requests defaults to ISO-8859-1 for text/* types if charset is missing.
    if response.encoding is None:
        response.encoding = "utf-8"
    elif response.encoding == "ISO-8859-1":
        content_type = response.headers.get("Content-Type", "").lower()
        if "charset" not in content_type:
            response.encoding = "utf-8"

    for line in response.iter_lines(decode_unicode=True):
        if should_cancel and should_cancel():
            return None, True

        if not line:
            continue

        # downloaded_bytes estimation (since we are decoding)
        downloaded_bytes += len(line.encode(response.encoding, errors="replace")) + 1
        stripped_line = line.strip()

        if not stripped_line or stripped_line.startswith(":"):
            continue

        if stripped_line.startswith("data: "):
            data_str = stripped_line[6:]
            if data_str == "[DONE]":
                break

            try:
                data = json.loads(data_str)

                # Use the provided parser if available
                chunk_text = None
                if stream_chunk_parser:
                    chunk_text = stream_chunk_parser(data)

                if chunk_text:
                    full_text += chunk_text
                    if progress_callback:
                        elapsed = time.time() - start_time
                        progress_data = LmProgressData(
                            stage=LmRequestStage.RECEIVING,
                            text_chunk=chunk_text,
                            total_chars=len(full_text),
                            total_bytes=downloaded_bytes,
                            elapsed=elapsed,
                            content_length=content_length,
                        )
                        progress_callback(progress_data)
            except json.JSONDecodeError:
                continue

        # If no text was extracted yet (e.g. still downloading), report byte progress
        if not full_text and progress_callback:
            elapsed = time.time() - start_time
            progress_data = LmProgressData(
                stage=LmRequestStage.RECEIVING,
                text_chunk="",
                total_chars=0,
                total_bytes=downloaded_bytes,
                elapsed=elapsed,
                content_length=content_length,
            )
            progress_callback(progress_data)

    # Return a simple JSON containing the full text to maintain compatibility with make_api_request_json
    return json.dumps({"content": full_text}, ensure_ascii=False).encode("utf-8"), False


def _handle_byte_stream(
    response: requests.Response,
    progress_callback: Optional[Callable[[LmProgressData], None]],
    chunk_size: int,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> tuple[bytes | None, bool]:
    """
    Handle regular byte streaming (for non-LLM requests or backward compatibility).

    Args:
        response: The streaming HTTP response
        progress_callback: Function to call with progress updates
        chunk_size: Size of chunks to read
        should_cancel: Optional callback to check if operation should be canceled.

    Returns:
        A tuple of (response_content, is_cancelled). response_content is bytes or None if cancelled.
    """
    content_length_header = response.headers.get("Content-Length")
    content_length = int(content_length_header) if content_length_header is not None and content_length_header.isdigit() else None
    downloaded = 0
    start_time = time.time()
    content_parts = []

    for chunk in response.iter_content(chunk_size=chunk_size):
        if should_cancel and should_cancel():
            return None, True

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
                total_chars=0,
                total_bytes=downloaded,
                elapsed=elapsed,
                content_length=content_length,
            )
            if progress_callback:
                progress_callback(progress_data)

    return b"".join(content_parts), False


def make_api_request_json(  # noqa: PLR0913
    url: str,
    method: str = "POST",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict[str, Any]] = None,
    json_data: Optional[dict[str, JSON_TYPE]] = None,
    connect_timeout: int = 10,
    read_timeout: int = 110,
    progress_callback: Optional[Callable[[LmProgressData], None]] = None,
    stream_chunk_parser: Optional[Callable[[dict[str, Any]], Optional[str]]] = None,
    chunk_size: int = 8192,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> tuple[dict[str, JSON_TYPE] | None, bool]:
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
        progress_callback: Function called with LmProgressData
        stream_chunk_parser: Optional function to extract text from SSE JSON data
        chunk_size: Size of chunks to read at a time for streaming
        should_cancel: Optional callback to check if operation should be canceled.

    Returns:
        A tuple of (parsed_json_response, is_cancelled). parsed_json_response is a dict or None if cancelled.

    Raises:
        requests.exceptions.Timeout: If the request times out
        requests.exceptions.HTTPError: If the HTTP response status code is not 2xx
        requests.exceptions.RequestException: For other request-related errors
        ValueError: If the response is not valid JSON or is not a JSON object (dict)
    """

    content, is_cancelled = make_api_request(
        url=url,
        method=method,
        headers=headers,
        data=data,
        json_data=json_data,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        progress_callback=progress_callback,
        stream_chunk_parser=stream_chunk_parser,
        chunk_size=chunk_size,
        should_cancel=should_cancel,
    )

    if is_cancelled or content is None:
        return None, True

    content_str = content.decode("utf-8")

    try:
        parsed = json.loads(content_str)
    except json.JSONDecodeError:
        raise

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object (dict), got {type(parsed).__name__}")

    return parsed, False
