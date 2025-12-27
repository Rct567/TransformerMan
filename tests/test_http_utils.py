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
            mock_request.return_value = mock_response

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
            mock_request.return_value = mock_response

            result, is_cancelled = make_api_request_json("https://api.example.com/json")
            assert result == {"status": "ok"}
            assert not is_cancelled

    def test_make_api_request_sse_openai_format(self) -> None:
        """Test SSE stream parsing with OpenAI-style format."""
        # Mock OpenAI-style SSE stream
        sse_chunks = [
            b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": " world"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.url = "https://api.openai.com/v1/chat/completions"
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "text/event-stream"}
            mock_response.iter_content.return_value = sse_chunks
            mock_request.return_value = mock_response

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
            mock_request.return_value = mock_response

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
        utf8_chunk = b'data: {"content": "El queso holand\xc3\xa9s"}\n\n'

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            # Default encoding for text/event-stream without charset is ISO-8859-1 in requests
            mock_response.encoding = "ISO-8859-1"
            mock_response.headers = {"Content-Type": "text/event-stream"}

            def mock_iter_content(chunk_size: int | None = None, decode_unicode: bool = False) -> Any:
                if decode_unicode:
                    yield utf8_chunk.decode(mock_response.encoding)
                else:
                    yield utf8_chunk

            mock_response.iter_content.side_effect = mock_iter_content
            mock_request.return_value = mock_response

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
        iso_chunk = b'data: {"content": "El queso holand\xe9s"}\n\n'

        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.encoding = "ISO-8859-1"
            # Explicit charset in header
            mock_response.headers = {"Content-Type": "text/event-stream; charset=ISO-8859-1"}

            def mock_iter_content(chunk_size: int | None = None, decode_unicode: bool = False) -> Any:
                if decode_unicode:
                    yield iso_chunk.decode(mock_response.encoding)
                else:
                    yield iso_chunk

            mock_response.iter_content.side_effect = mock_iter_content
            mock_request.return_value = mock_response

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
