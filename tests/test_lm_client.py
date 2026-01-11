from __future__ import annotations

from typing import TYPE_CHECKING

from unittest.mock import patch

from transformerman.lib.lm_clients import (
    ApiKey,
    DeepSeekLMClient,
    DummyLMClient,
    GeminiLMClient,
    GrokLMClient,
    ModelName,
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
