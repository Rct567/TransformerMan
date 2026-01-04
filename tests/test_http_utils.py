from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from transformerman.lib.http_utils import (
    LmProgressData,
    LmRequestStage,
    make_api_request,
    make_api_request_json,
)


class TestHttpUtils:
    """Test class for HTTP utility functions."""

    def test_make_api_request_basic(self) -> None:
        """Test basic API request with successful response."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.content = b"hello world"
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_request.return_value.__enter__.return_value = mock_response

            result, is_cancelled = make_api_request("https://api.example.com/test", method="POST")
            assert result == b"hello world"
            assert not is_cancelled

    def test_make_api_request_json_basic(self) -> None:
        """Test basic JSON API request with successful response."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.content = json.dumps({"status": "ok"}).encode("utf-8")
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "application/json"}
            mock_request.return_value.__enter__.return_value = mock_response

            result, is_cancelled = make_api_request_json("https://api.example.com/json")
            assert result == {"status": "ok"}
            assert not is_cancelled

    def test_make_api_request_sse_openai_format(self) -> None:
        """Test SSE stream parsing with OpenAI-style format."""
        # Mock OpenAI-style SSE stream
        sse_chunks = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
            'data: {"choices": [{"delta": {"content": " world"}}]}\n\n',
            "data: [DONE]\n\n",
        ]

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.url = "https://api.openai.com/v1/chat/completions"
            mock_response.status_code = 200
            mock_response.encoding = "utf-8"
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_response.iter_lines.return_value = sse_chunks
            mock_request.return_value.__enter__.return_value = mock_response

            progress_updates: list[LmProgressData] = []

            def progress_callback(data: LmProgressData) -> None:
                progress_updates.append(data)

            def openai_parser(data: dict[str, Any]) -> str | None:
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0].get("delta", {}).get("content")
                return None

            result, is_cancelled = make_api_request_json(
                "https://api.openai.com/v1/chat/completions",
                json_data={"stream": True},
                progress_callback=progress_callback,
                stream_chunk_parser=openai_parser,
            )

            # Check if progress updates were received
            receiving_updates = [u for u in progress_updates if u.stage == LmRequestStage.RECEIVING and u.text_chunk]
            assert len(receiving_updates) >= 2
            assert receiving_updates[0].text_chunk == "Hello"
            assert receiving_updates[1].text_chunk == " world"

            # Check final result (new format returns {"content": "..."})
            assert result is not None
            assert result["content"] == "Hello world"
            assert not is_cancelled

    def test_make_api_request_http_error(self) -> None:
        """Test that HTTP errors are correctly raised."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
            mock_request.return_value.__enter__.return_value = mock_response

            with pytest.raises(requests.exceptions.HTTPError):
                make_api_request("https://api.example.com/error")

    def test_make_api_request_timeout(self) -> None:
        """Test that timeouts are correctly raised."""
        with patch("requests.request") as mock_request:
            mock_request.side_effect = requests.exceptions.Timeout("Timeout")

            with pytest.raises(requests.exceptions.Timeout):
                make_api_request("https://api.example.com/timeout")

    def test_make_api_request_sse_utf8_encoding(self) -> None:
        """Test that SSE streams default to UTF-8 if no charset is specified."""
        # "El queso holandés" in UTF-8
        utf8_chunk = 'data: {"content": "El queso holandés"}\n\n'

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            # Default encoding for text/event-stream without charset is ISO-8859-1 in requests
            mock_response.encoding = "ISO-8859-1"
            mock_response.headers = {"Content-Type": "text/event-stream"}

            mock_response.iter_lines.return_value = [utf8_chunk]
            mock_request.return_value.__enter__.return_value = mock_response

            result, is_cancelled = make_api_request_json(
                "https://api.example.com/sse",
                json_data={"stream": True},
                stream_chunk_parser=lambda d: d.get("content"),
            )

            # Should have forced to utf-8
            assert result is not None
            assert result["content"] == "El queso holandés"
            assert not is_cancelled
            assert mock_response.encoding == "utf-8"

    def test_make_api_request_sse_explicit_charset(self) -> None:
        """Test that explicit charsets in Content-Type are respected."""
        # "El queso holandés" in ISO-8859-1 is b'El queso holand\xe9s'
        # In a JSON context: {"content": "El queso holand\xe9s"}
        iso_chunk = 'data: {"content": "El queso holandés"}\n\n'

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.encoding = "ISO-8859-1"
            # Explicit charset in header
            mock_response.headers = {"Content-Type": "text/event-stream; charset=ISO-8859-1"}

            mock_response.iter_lines.return_value = [iso_chunk]
            mock_request.return_value.__enter__.return_value = mock_response

            result, is_cancelled = make_api_request_json(
                "https://api.example.com/sse",
                json_data={"stream": True},
                stream_chunk_parser=lambda d: d.get("content"),
            )

            # Should have respected ISO-8859-1
            assert result is not None
            assert result["content"] == "El queso holandés"
            assert not is_cancelled
            assert mock_response.encoding == "ISO-8859-1"

    def test_make_api_request_cancellation(self) -> None:
        """Test cancellation in make_api_request."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_request.return_value.__enter__.return_value = mock_response

            # Test cancellation when progress_callback is None
            result, is_cancelled = make_api_request(
                "https://api.example.com/test",
                should_cancel=lambda: True
            )
            assert result is None
            assert is_cancelled

    def test_make_api_request_sse_cancellation(self) -> None:
        """Test cancellation during SSE streaming after some data."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_response.encoding = "utf-8"
            # Multiple chunks
            mock_response.iter_lines.return_value = [
                "data: chunk 1\n\n",
                "data: chunk 2\n\n",
                "data: chunk 3\n\n"
            ]
            mock_request.return_value.__enter__.return_value = mock_response

            # Cancel after the first chunk
            call_count = 0

            def should_cancel() -> bool:
                nonlocal call_count
                call_count += 1
                return call_count > 1

            result, is_cancelled = make_api_request(
                "https://api.example.com/sse",
                json_data={"stream": True},
                should_cancel=should_cancel
            )
            assert result is None
            assert is_cancelled
            assert call_count == 2  # Once at start of loop, once after first chunk

    def test_handle_byte_stream(self) -> None:
        """Test _handle_byte_stream with progress callback."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Length": "10"}
            mock_response.iter_content.return_value = [b"hello", b"world"]
            mock_request.return_value.__enter__.return_value = mock_response

            progress_updates: list[LmProgressData] = []

            def progress_callback(data: LmProgressData) -> None:
                progress_updates.append(data)

            result, is_cancelled = make_api_request(
                "https://api.example.com/bytes",
                progress_callback=progress_callback,
                chunk_size=5
            )

            assert result == b"helloworld"
            assert not is_cancelled
            assert len(progress_updates) == 3  # 1 sending + 2 receiving
            assert progress_updates[1].total_bytes == 5
            assert progress_updates[2].total_bytes == 10

    def test_handle_byte_stream_cancellation(self) -> None:
        """Test cancellation during byte streaming after some data."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.encoding = "utf-8"
            # Multiple chunks
            mock_response.iter_content.return_value = [b"hello", b"world", b"extra"]
            mock_request.return_value.__enter__.return_value = mock_response

            # Cancel after the first chunk
            call_count = 0

            def should_cancel() -> bool:
                nonlocal call_count
                call_count += 1
                return call_count > 1

            result, is_cancelled = make_api_request(
                "https://api.example.com/bytes",
                progress_callback=lambda _: None,
                should_cancel=should_cancel
            )
            assert result is None
            assert is_cancelled
            assert call_count == 2

    def test_make_api_request_json_cancellation(self) -> None:
        """Test cancellation in make_api_request_json."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_request.return_value.__enter__.return_value = mock_response

            result, is_cancelled = make_api_request_json(
                "https://api.example.com/json",
                should_cancel=lambda: True
            )
            assert result is None
            assert is_cancelled

    def test_make_api_request_sse_edge_cases(self) -> None:
        """Test SSE edge cases like empty lines, comments, and invalid JSON."""
        sse_chunks = [
            "",  # Empty line
            ": comment\n",  # Comment
            "data: invalid json\n\n",
            'data: {"content": "valid"}\n\n',
        ]

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_response.iter_lines.return_value = sse_chunks
            mock_response.encoding = "utf-8"
            mock_request.return_value.__enter__.return_value = mock_response

            result, is_cancelled = make_api_request_json(
                "https://api.example.com/sse",
                json_data={"stream": True},
                stream_chunk_parser=lambda d: d.get("content"),
            )

            assert result == {"content": "valid"}
            assert not is_cancelled

    def test_make_api_request_json_errors(self) -> None:
        """Test error cases for make_api_request_json."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "application/json"}
            mock_request.return_value.__enter__.return_value = mock_response

            # Invalid JSON
            mock_response.content = b"invalid json"
            with pytest.raises(json.JSONDecodeError):
                make_api_request_json("https://api.example.com/json")

            # Non-dict JSON
            mock_response.content = b"[1, 2, 3]"
            with pytest.raises(ValueError, match="Expected JSON object"):
                make_api_request_json("https://api.example.com/json")

    def test_make_api_request_sse_no_text_progress(self) -> None:
        """Test SSE progress reporting when no text is extracted yet."""
        sse_chunks = [
            'data: {"other": "data"}\n\n',  # No content extracted by parser
        ]

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_response.iter_lines.return_value = sse_chunks
            mock_response.encoding = "utf-8"
            mock_request.return_value.__enter__.return_value = mock_response

            progress_updates: list[LmProgressData] = []

            def progress_callback(data: LmProgressData) -> None:
                progress_updates.append(data)

            make_api_request(
                "https://api.example.com/sse",
                json_data={"stream": True},
                progress_callback=progress_callback,
                stream_chunk_parser=lambda d: d.get("content"),
            )

            # Should have received a progress update even without text
            receiving_updates = [u for u in progress_updates if u.stage == LmRequestStage.RECEIVING]
            assert len(receiving_updates) > 0
            assert receiving_updates[0].text_chunk == ""
            assert receiving_updates[0].total_bytes > 0

    def test_make_api_request_sse_default_encoding(self) -> None:
        """Test that SSE streams default to UTF-8 if encoding is None."""
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_response.encoding = None  # Force default logic
            mock_response.iter_lines.return_value = ['data: {"content": "test"}\n\n']
            mock_request.return_value.__enter__.return_value = mock_response

            make_api_request_json(
                "https://api.example.com/sse",
                json_data={"stream": True},
                stream_chunk_parser=lambda d: d.get("content"),
            )

            assert mock_response.encoding == "utf-8"
