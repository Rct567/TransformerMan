import pytest
from transformerman.lib.transform_prompt_builder import TransformPromptBuilder
from transformerman.lib.selected_notes import NoteModel, SelectedNotesFromType
from transformerman.lib.transform_operations import NoteTransformer
from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName
from transformerman.lib.response_middleware import ResponseMiddleware, LogLastRequestResponseMiddleware
from transformerman.ui.transform.field_widgets import FieldSelection
from tests.tools import test_collection as test_collection_fixture, with_test_collection, TestCollection

from pathlib import Path
from transformerman.lib.addon_config import AddonConfig

col = test_collection_fixture


@pytest.fixture
def response_middleware(addon_config: AddonConfig, user_files_dir: Path) -> ResponseMiddleware:
    """Create a TransformMiddleware with LmLoggingMiddleware for testing."""
    middleware = ResponseMiddleware()
    lm_logging = LogLastRequestResponseMiddleware(addon_config, user_files_dir)
    middleware.register(lm_logging)
    return middleware


class TestPromptInterception:
    @with_test_collection("empty_collection")
    def test_prompt_builder_template_generation(self, col: TestCollection) -> None:
        # Setup: Create a note type and a note
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        note = col.new_note(model)
        note["Front"] = "Front content"
        note["Back"] = ""  # Empty field to fill
        col.add_note(note, deck_id)

        selected_notes = SelectedNotesFromType(col, [note.id], NoteModel(col, model))

        prompt_builder = TransformPromptBuilder(col)
        # In the UI, writable fields are always also in 'selected'
        field_selection = FieldSelection(selected=["Front", "Back"], writable=["Back"], overwritable=[])

        # Test template generation
        template = prompt_builder.build_prompt_template(selected_notes, field_selection, max_examples=0)
        assert "{target_notes_xml}" in template
        assert "Instructions:" in template

        # Test renderer from template
        renderer = prompt_builder.get_renderer_from_template(template, selected_notes, field_selection)
        rendered_prompt = renderer(None)
        assert f'<note nid="{note.id}"' in rendered_prompt
        assert '<field name="Back"></field>' in rendered_prompt
        assert "{target_notes_xml}" not in rendered_prompt

    @with_test_collection("empty_collection")
    def test_note_transformer_interceptor(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        response_middleware: ResponseMiddleware,
        user_files_dir: Path,
    ) -> None:
        # Setup: Create a note type and a note
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        note = col.new_note(model)
        note["Front"] = "Front content"
        note["Back"] = ""  # Empty field to fill
        col.add_note(note, deck_id)

        selected_notes = SelectedNotesFromType(col, [note.id], NoteModel(col, model))

        prompt_builder = TransformPromptBuilder(col)
        # In the UI, writable fields are always also in 'selected'
        field_selection = FieldSelection(selected=["Front", "Back"], writable=["Back"], overwritable=[])

        # Use real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        # Define interceptor
        def interceptor(template: str) -> str:
            return template + "\n[INTERCEPTED]"

        # Enable logging to verify the prompt
        addon_config.update_setting("log_last_lm_response_request", True)
        logging_middleware = response_middleware.get(LogLastRequestResponseMiddleware)
        assert logging_middleware is not None
        # We need to manually enable it because it was initialized with log_enabled=False
        logging_middleware.log_enabled = True

        # Ensure the logs directory exists (it's under user_files_dir)
        logs_dir = user_files_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize NoteTransformer with interceptor
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            lm_client=dummy_client,
            prompt_builder=prompt_builder,
            field_selection=field_selection,
            addon_config=addon_config,
            middleware=response_middleware,
            prompt_interceptor=interceptor,
        )

        # Verify template was modified
        assert "[INTERCEPTED]" in transformer.prompt_template

        # Verify batching uses the modified template
        results, field_updates = transformer.get_field_updates()

        # Check results
        assert results.error is None
        assert results.num_notes_updated == 1
        assert len(field_updates) == 1
        assert note.id in field_updates
        assert field_updates[note.id]["Back"] == "Lorem ipsum dolor sit amet, consectetur adipiscing elit."

        # Verify the prompt actually sent to the client contained the interception string
        # using the LogLastRequestResponseMiddleware
        log_file = logs_dir / "last_lm_request_response.log"
        assert log_file.exists()
        log_content = log_file.read_text(encoding="utf-8")
        assert "[INTERCEPTED]" in log_content

    @with_test_collection("empty_collection")
    def test_note_transformer_interceptor_cancel(
        self,
        col: TestCollection,
        addon_config: AddonConfig,
        response_middleware: ResponseMiddleware,
    ) -> None:
        # Setup: Create a note type and a note
        model = col.models.by_name("Basic")
        assert model is not None
        deck_id = col.decks.id_for_name("Default")
        assert deck_id

        note = col.new_note(model)
        note["Front"] = "Front content"
        note["Back"] = ""
        col.add_note(note, deck_id)

        selected_notes = SelectedNotesFromType(col, [note.id], NoteModel(col, model))

        prompt_builder = TransformPromptBuilder(col)
        field_selection = FieldSelection(selected=["Front", "Back"], writable=["Back"], overwritable=[])

        # Use real DummyLMClient
        dummy_client = DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))

        def interceptor(template: str) -> str:
            raise Exception("Canceled")

        with pytest.raises(Exception, match="Canceled"):
            NoteTransformer(
                col=col,
                selected_notes=selected_notes,
                lm_client=dummy_client,
                prompt_builder=prompt_builder,
                field_selection=field_selection,
                addon_config=addon_config,
                middleware=response_middleware,
                prompt_interceptor=interceptor,
            )
