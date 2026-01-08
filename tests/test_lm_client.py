"""
Tests for LM client.
"""

from __future__ import annotations

from unittest.mock import patch

from transformerman.lib.lm_clients import (
    ApiKey,
    DeepSeekLMClient,
    DummyLMClient,
    GeminiLMClient,
    GrokLMClient,
    ModelName,
)


class TestLmClient:
    """Test class for LM client."""

    def test_dummy_client_basic_response(self) -> None:
        """Test that DummyLMClient returns valid XML response."""
        client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        prompt = """<notes model="Basic">
  <note nid="123" deck="Test Deck">
    <field name="Front">Hello</field>
    <field name="Back"></field>
  </note>
</notes>"""

        response = client.process_prompt(prompt)

        assert '<notes model="Basic">' in response.content
        assert 'nid="123"' in response.content
        assert '<field name="Front">Hello</field>' in response.content
        assert '<field name="Back">Lorem ipsum dolor sit amet, consectetur adipiscing elit.</field>' in response.content

    def test_dummy_client_multiple_notes(self) -> None:
        """Test DummyLMClient with multiple notes."""
        client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        prompt = """<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Q1</field>
    <field name="Back"></field>
  </note>
  <note nid="456" deck="Test">
    <field name="Front">Q2</field>
    <field name="Back"></field>
  </note>
</notes>"""

        response = client.process_prompt(prompt)

        assert 'nid="123"' in response.content
        assert 'nid="456"' in response.content
        assert response.content.count("Lorem ipsum dolor sit amet, consectetur adipiscing elit.") == 2

    def test_dummy_client_preserves_existing_content(self) -> None:
        """Test that DummyLMClient preserves existing field content."""
        client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        prompt = """<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Existing Front</field>
    <field name="Back">Existing Back</field>
  </note>
</notes>"""

        response = client.process_prompt(prompt)

        assert '<field name="Front">Existing Front</field>' in response.content
        assert '<field name="Back">Existing Back</field>' in response.content
        assert "Lorem ipsum" not in response.content

    def test_dummy_client_empty_prompt(self) -> None:
        """Test DummyLMClient with empty prompt."""
        client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        response = client.process_prompt("")

        assert response.content == "<notes></notes>"

    def test_gemini_client_request_construction(self) -> None:
        """Test GeminiLMClient request construction."""
        model = GeminiLMClient.get_available_models()[0]
        client = GeminiLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
            assert kwargs["headers"]["x-goog-api-key"] == "test-key"
            assert kwargs["json_data"] == {"contents": [{"parts": [{"text": "test prompt"}]}]}

    def test_deepseek_client_request_construction(self) -> None:
        """Test DeepSeekLMClient request construction."""
        model = DeepSeekLMClient.get_available_models()[0]
        client = DeepSeekLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://api.deepseek.com/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"

    def test_grok_client_request_construction(self) -> None:
        """Test GrokLMClient request construction."""
        model = GrokLMClient.get_available_models()[0]
        client = GrokLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://api.x.ai/v1/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"
