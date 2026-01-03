import pytest
from unittest.mock import MagicMock
from transformerman.lib.prompt_builder import PromptBuilder
from transformerman.lib.selected_notes import SelectedNotesFromType, NoteModel
from transformerman.lib.transform_operations import NoteTransformer
from transformerman.ui.field_widgets import FieldSelection
from tests.tools import test_collection as test_collection_fixture, with_test_collection, TestCollection

col = test_collection_fixture


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

        prompt_builder = PromptBuilder(col)
        field_selection = FieldSelection(selected=["Front"], writable=["Back"], overwritable=[])

        # Test template generation
        template = prompt_builder.build_prompt_template(selected_notes, field_selection, max_examples=0)
        assert "{target_notes_xml}" in template
        assert "Instructions:" in template

        # Test renderer from template
        renderer = prompt_builder.get_renderer_from_template(template, selected_notes, field_selection)
        rendered_prompt = renderer(None)
        assert f'<note nid="{note.id}"' in rendered_prompt
        assert "{target_notes_xml}" not in rendered_prompt

    @with_test_collection("empty_collection")
    def test_note_transformer_interceptor(self, col: TestCollection) -> None:
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

        prompt_builder = PromptBuilder(col)
        field_selection = FieldSelection(selected=["Front"], writable=["Back"], overwritable=[])

        addon_config = MagicMock()
        addon_config.get_max_prompt_size.return_value = 1000
        addon_config.get_max_examples.return_value = 0

        lm_client = MagicMock()
        # Mock successful response
        lm_client.transform.return_value = MagicMock(is_canceled=False, error=None)
        lm_client.transform.return_value.get_notes_from_xml.return_value = {}

        transform_middleware = MagicMock()

        # Define interceptor
        def interceptor(template: str) -> str:
            return template + "\n[INTERCEPTED]"

        # Initialize NoteTransformer with interceptor
        transformer = NoteTransformer(
            col=col,
            selected_notes=selected_notes,
            lm_client=lm_client,
            prompt_builder=prompt_builder,
            field_selection=field_selection,
            addon_config=addon_config,
            transform_middleware=transform_middleware,
            prompt_interceptor=interceptor,
        )

        # Verify template was modified
        assert "[INTERCEPTED]" in transformer.prompt_template

        # Verify batching uses the modified template
        transformer.get_field_updates()

        # Check what was passed to lm_client.transform
        call_args = lm_client.transform.call_args
        assert call_args is not None
        prompt_arg = call_args[0][0]
        assert "[INTERCEPTED]" in prompt_arg

    @with_test_collection("empty_collection")
    def test_note_transformer_interceptor_cancel(self, col: TestCollection) -> None:
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

        prompt_builder = PromptBuilder(col)
        field_selection = FieldSelection(selected=["Front"], writable=["Back"], overwritable=[])

        addon_config = MagicMock()
        addon_config.get_max_prompt_size.return_value = 1000
        addon_config.get_max_examples.return_value = 0

        lm_client = MagicMock()
        transform_middleware = MagicMock()

        def interceptor(template: str) -> str:
            raise Exception("Canceled")

        with pytest.raises(Exception, match="Canceled"):
            NoteTransformer(
                col=col,
                selected_notes=selected_notes,
                lm_client=lm_client,
                prompt_builder=prompt_builder,
                field_selection=field_selection,
                addon_config=addon_config,
                transform_middleware=transform_middleware,
                prompt_interceptor=interceptor,
            )
