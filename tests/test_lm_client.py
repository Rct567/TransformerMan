from __future__ import annotations

from typing import TYPE_CHECKING

from unittest.mock import patch

from transformerman.lib.lm_clients import (
    ApiKey,
    ClaudeLMClient,
    CustomOpenAi,
    DeepSeekLMClient,
    DummyLMClient,
    GeminiLMClient,
    GroqLMClient,
    GrokLMClient,
    LmStudio,
    ModelName,
    OpenAILMClient,
)
from transformerman.lib.selected_notes import SelectedNotes
from transformerman.lib.transform_prompt_builder import TransformPromptBuilder
from transformerman.lib.utilities import is_lorem_ipsum_text
from transformerman.lib.xml_parser import new_notes_from_xml, notes_from_xml
from transformerman.lib.generation_prompt_builder import GenerationPromptBuilder
from transformerman.lib.collection_data import NoteModel
from transformerman.ui.transform.field_widgets import FieldSelection

if TYPE_CHECKING:
    from tests.tools import TestCollection

from tests.tools import with_test_collection, TestCollection, test_collection as test_collection_fixture

col = test_collection_fixture


class TestLmClient:
    """Test class for LM client."""

    @with_test_collection("two_deck_collection")
    def test_dummy_client_transformation_notes(self, col: TestCollection) -> None:

        client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))
        note_ids = sorted(col.find_notes(""))
        assert len(note_ids) >= 1
        note_id = note_ids[0]
        note = col.get_note(note_id)
        note["Front"] = ""  # Empty field
        col.update_note(note)

        selected_notes = SelectedNotes(col, [note_id])
        builder = TransformPromptBuilder(col)

        # Set field instructions
        instructions = {"Front": "Provide a concise question", "Back": "Provide detailed answer"}
        builder.update_field_instructions(instructions)

        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        # Build prompt
        prompt = builder.get_prompt_renderer(
            target_notes=selected_notes.filter_by_note_type(note_type),
            field_selection=FieldSelection(
                selected=["Front", "Back"],
                writable=["Front"],
                overwritable=[],
            ),
            max_examples=3,
        )(None)

        response = client.process_prompt(prompt)
        assert response.content
        assert not response.error

        field_updates = notes_from_xml(response.content)
        assert len(field_updates) == 1
        assert note_id in field_updates
        assert "Front" in field_updates[note_id]
        assert is_lorem_ipsum_text(field_updates[note_id]["Front"])

    @with_test_collection("empty_collection")
    def test_dummy_client_generation_response(self, col: TestCollection) -> None:
        """Test that DummyLMClient handles generation prompts."""

        client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        prompt_builder = GenerationPromptBuilder(col)

        note_type = NoteModel.by_name(col, "Basic")
        assert note_type

        prompt = prompt_builder.build_prompt(
            source_text="Python programming language",
            note_type=note_type,
            deck_name="Default",
            target_count=2,
            selected_fields=None,
            example_notes=None,
            max_examples=0,
        )

        response = client.process_prompt(prompt)
        assert response.content
        assert not response.error

        notes = new_notes_from_xml(response.content)

        assert len(notes) == 2
        assert notes[0].model_name == "Basic"
        assert notes[0].deck_name == "Default"
        assert "Front" in notes[0]
        assert "Back" in notes[0]
        assert is_lorem_ipsum_text(notes[0]["Front"])

    def test_gemini_client_request_construction(self) -> None:
        """Test GeminiLMClient request construction."""
        model = GeminiLMClient.get_recommended_models()[0]
        client = GeminiLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert "https://generativelanguage.googleapis.com/" in kwargs["url"]
            assert kwargs["headers"]["x-goog-api-key"] == "test-key"
            assert kwargs["json_data"] == {"contents": [{"parts": [{"text": "test prompt"}]}]}

    def test_deepseek_client_request_construction(self) -> None:
        """Test DeepSeekLMClient request construction."""
        model = DeepSeekLMClient.get_recommended_models()[0]
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
        model = GrokLMClient.get_recommended_models()[0]
        client = GrokLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://api.x.ai/v1/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"

    def test_lm_studio_fetch_endpoint(self) -> None:
        """Test that LmStudio constructs the correct endpoint from port."""
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"data": [{"id": "local-model"}]}
            mock_get.return_value.status_code = 200

            # Test default port
            client = LmStudio(ApiKey("dummy_key"), model=None, custom_settings={})
            assert client.fetch_available_models()
            args, _ = mock_get.call_args
            assert args[0] == "http://127.0.0.1:1234/v1/models"

            # Test custom port
            client = LmStudio(ApiKey("dummy_key"), model=None, custom_settings={"port": "5678"})
            assert client.fetch_available_models()
            args, _ = mock_get.call_args
            assert args[0] == "http://127.0.0.1:5678/v1/models"

    def test_openai_client_request_construction(self) -> None:
        """Test OpenAILMClient request construction."""
        model = OpenAILMClient.get_recommended_models()[0]
        client = OpenAILMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://api.openai.com/v1/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"

    def test_claude_client_request_construction(self) -> None:
        """Test ClaudeLMClient request construction."""
        model = ClaudeLMClient.get_recommended_models()[0]
        client = ClaudeLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://api.anthropic.com/v1/messages"
            assert kwargs["headers"]["x-api-key"] == "test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"

    def test_groq_client_request_construction(self) -> None:
        """Test GroqLMClient request construction."""
        model = GroqLMClient.get_recommended_models()[0]
        client = GroqLMClient(ApiKey("test-key"), ModelName(model))

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://api.groq.com/openai/v1/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"

    def test_custom_openai_client_request_construction(self) -> None:
        """Test CustomOpenAi request construction."""
        model = ModelName("test-model")
        client = CustomOpenAi(ApiKey("test-key"), model, custom_settings={"end_point": "https://custom.openai.com/v1"})

        with patch("transformerman.lib.lm_clients.make_api_request_json") as mock_request:
            mock_request.return_value = {"content": "test response"}
            client.process_prompt("test prompt")

            _, kwargs = mock_request.call_args
            assert kwargs["url"] == "https://custom.openai.com/v1/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json_data"]["model"] == model
            assert kwargs["json_data"]["messages"][0]["content"] == "test prompt"
