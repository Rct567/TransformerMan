"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.

HTTP utilities for making API requests with progress callbacks.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Callable, NamedTuple, Optional

import requests

if TYPE_CHECKING:
    from transformerman.lib.utilities import JSON_TYPE


class ProgressData(NamedTuple):
    """Data passed to progress callbacks during HTTP downloads."""
    downloaded: int
    total_size: Optional[int]
    bytes_per_second: float
    elapsed: float


def make_api_request(
    url: str,
    method: str = "POST",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict[str, Any]] = None,
    json_data: Optional[dict[str, JSON_TYPE]] = None,
    connect_timeout: int = 10,
    read_timeout: int = 110,
    progress_callback: Optional[Callable[[ProgressData], None]] = None,
    chunk_size: int = 8192
) -> bytes:
    """
    Make an HTTP request with progress callback support.

    Args:
        url: The URL to request
        method: HTTP method (GET, POST, etc.)
        headers: HTTP headers to include
        data: Form data to send (for form-encoded POST)
        json_data: JSON data to send (for JSON POST)
        connect_timeout: Connection timeout in seconds
        read_timeout: Read timeout in seconds
        progress_callback: Function called with ProgressData(downloaded, total_size, bytes_per_second, elapsed)
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

    # Make the request with parameters based on what's provided
    if json_data is not None:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_data,
            timeout=(connect_timeout, read_timeout),
            stream=progress_callback is not None
        )
    elif data is not None:
        response = requests.request(
            method,
            url,
            headers=headers,
            data=data,
            timeout=(connect_timeout, read_timeout),
            stream=progress_callback is not None
        )
    else:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=(connect_timeout, read_timeout),
            stream=progress_callback is not None
        )
    response.raise_for_status()  # Raise exception for bad status codes

    # If no progress callback, read the entire response
    if progress_callback is None:
        return response.content

    # Stream the response with progress callback
    content_length = response.headers.get('Content-Length')
    total_size = int(content_length) if content_length is not None else None
    downloaded = 0
    start_time = time.time()
    content_parts = []

    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:  # filter out keep-alive new chunks
            content_parts.append(chunk)
            downloaded += len(chunk)

            # Calculate metrics
            elapsed = time.time() - start_time
            bytes_per_second = downloaded / elapsed if elapsed > 0 else 0

            # Call the callback with ProgressData
            progress_data = ProgressData(
                downloaded=downloaded,
                total_size=total_size,
                bytes_per_second=bytes_per_second,
                elapsed=elapsed
            )
            progress_callback(progress_data)

    return b''.join(content_parts)


def make_api_request_json(
    url: str,
    method: str = "POST",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict] = None,
    json_data: Optional[dict] = None,
    connect_timeout: int = 10,
    read_timeout: int = 110,
    progress_callback: Optional[Callable[[ProgressData], None]] = None,
    chunk_size: int = 8192
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
        progress_callback: Function called with ProgressData(downloaded, total_size, bytes_per_second, elapsed)
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
        url=url,
        method=method,
        headers=headers,
        data=data,
        json_data=json_data,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        progress_callback=progress_callback,
        chunk_size=chunk_size
    )

    parsed = json.loads(content.decode('utf-8'))

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object (dict), got {type(parsed).__name__}")

    return parsed
