"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, NamedTuple

from aqt import mw
from aqt.operations import QueryOp

from ...lib.note_generator import NoteGenerator
from ..progress_dialog import ProgressDialog
from ..prompt_preview_dialog import PromptPreviewDialog

if TYPE_CHECKING:
    from collections.abc import Sequence, MutableMapping, Iterable
    from aqt.qt import QWidget
    from anki.collection import Collection
    from anki.notes import Note, NoteId
    from ...lib.lm_clients import LMClient
    from ...lib.response_middleware import ResponseMiddleware
    from ...lib.selected_notes import NoteModel, SelectedNotesFromType
    from ...lib.xml_parser import NewNote
    from ...lib.http_utils import LmProgressData


class GenerationRequest(NamedTuple):
    """Parameters for a note generation request."""

    source_text: str
    note_type: NoteModel
    deck_name: str
    target_count: int
    selected_fields: list[str]
    example_notes: SelectedNotesFromType | None


class NotesGenerator:
    """
    Manages note generation with progress tracking and prompt preview.
    UI-side wrapper for the library NoteGenerator.
    """

    def __init__(self, col: Collection, lm_client: LMClient, middleware: ResponseMiddleware) -> None:
        self.col = col
        self.lm_client = lm_client
        self.middleware = middleware
        self.generator = NoteGenerator(col, lm_client, middleware)

    def generate(
        self,
        parent: QWidget,
        request: GenerationRequest,
        on_success: Callable[[Sequence[NewNote], dict[int, list[str]], int], None],
        on_failure: Callable[[Exception], None],
        prompt_interceptor: bool = False,
    ) -> None:
        """
        Generate notes with progress tracking and optional prompt preview.
        """
        # Build initial prompt
        prompt = self.generator.prompt_builder.build_prompt(
            source_text=request.source_text,
            note_type=request.note_type,
            deck_name=request.deck_name,
            target_count=request.target_count,
            selected_fields=request.selected_fields,
            example_notes=request.example_notes,
        )

        # Handle prompt preview if requested
        if prompt_interceptor:
            dialog = PromptPreviewDialog(parent, prompt)
            if dialog.exec():
                prompt = dialog.get_template() or ""
            else:
                # Canceled by user
                on_failure(Exception("Prompt preview canceled by user"))
                return

        # Create progress dialog
        progress = ProgressDialog(1, parent)
        progress.show()

        def generate_op(col: Collection) -> tuple[Sequence[NewNote], dict[int, list[str]], int]:
            def progress_callback(data: LmProgressData) -> None:
                def update_ui() -> None:
                    progress.update_progress(0, 1, data)

                if mw and mw.taskman:
                    mw.taskman.run_on_main(update_ui)

            def should_cancel() -> bool:
                return progress.is_cancel_requested()

            raw_notes = self.generator.generate_notes(
                source_text=request.source_text,
                note_type=request.note_type,
                deck_name=request.deck_name,
                target_count=request.target_count,
                selected_fields=request.selected_fields,
                example_notes=request.example_notes,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
                prompt=prompt,
            )

            def set_progress_to_filter_duplicates() -> None:
                progress.setLabelText("Checking for duplicate content...")
                progress.setValue(1)

            if mw and mw.taskman:
                mw.taskman.run_on_main(set_progress_to_filter_duplicates)

            model_fields = request.note_type.get_fields()
            all_duplicates = find_duplicates(col, raw_notes, request.deck_name, model_fields)
            model_fields_set = set(model_fields)
            filtered_notes: list[NewNote] = []
            duplicates: dict[int, list[str]] = {}
            ignored_count = 0

            for i, note in enumerate(raw_notes):
                duplicate_fields = all_duplicates.get(i, [])
                actual_note_fields = [k for k in note if k in model_fields_set]

                if duplicate_fields and len(duplicate_fields) == len(actual_note_fields):
                    ignored_count += 1
                else:
                    if duplicate_fields:
                        duplicates[len(filtered_notes)] = duplicate_fields
                    filtered_notes.append(note)

            return filtered_notes, duplicates, ignored_count

        def on_success_callback(result: tuple[Sequence[NewNote], dict[int, list[str]], int]) -> None:
            progress.cleanup()
            on_success(*result)

        def on_failure_callback(e: Exception) -> None:
            progress.cleanup()
            on_failure(e)

        QueryOp(
            parent=parent,
            op=generate_op,
            success=on_success_callback,
        ).failure(on_failure_callback).run_in_background()


def find_duplicates(
    col: Collection, notes: Sequence[MutableMapping[str, str]], deck_name: str, field_names: Sequence[str] | None = None
) -> dict[int, list[str]]:
    """
    Find duplicates for a list of notes within a specific deck.
    Returns a dict mapping relative row index to a list of duplicate field names.
    """
    duplicates: dict[int, list[str]] = {}
    batch_size = 10

    for batch_start in range(0, len(notes), batch_size):
        batch_end = min(batch_start + batch_size, len(notes))
        batch_notes = notes[batch_start:batch_end]

        batch_note_ids = get_duplicate_note_ids(col, batch_notes, deck_name, field_names)

        if not batch_note_ids:
            continue

        existing_notes = {nid: col.get_note(nid) for nid in batch_note_ids}

        for i, note in enumerate(batch_notes):
            note_index = batch_start + i
            duplicate_fields = _find_duplicate_fields_in_notes(note, existing_notes.values())

            if duplicate_fields:
                duplicates[note_index] = duplicate_fields

    return duplicates


def _find_duplicate_fields_in_notes(note: MutableMapping[str, str], existing_notes: Iterable[Note]) -> list[str]:
    """Helper function to find which fields in a note have duplicates in existing notes."""
    duplicate_fields = []

    for existing_note in existing_notes:
        for field, value in note.items():
            if field in existing_note and existing_note[field] == value:
                if field not in duplicate_fields:
                    duplicate_fields.append(field)

    return duplicate_fields


def get_duplicate_note_ids(
    col: Collection, notes: Sequence[MutableMapping[str, str]], deck_name: str, field_names: Sequence[str] | None = None
) -> Sequence[NoteId]:
    """Get all potential duplicate note IDs for a list of notes."""
    if not notes:
        return []

    note_queries = []
    for note in notes:
        field_parts = []
        for field, value in note.items():
            if field_names is not None and field not in field_names:
                continue

            if not value.strip():
                continue
            escaped_value = value.replace('"', '\\"')
            field_parts.append(f'"{field}:{escaped_value}"')

        if field_parts:
            note_queries.append(f"({' OR '.join(field_parts)})")

    if not note_queries:
        return []

    root_deck_name_escaped = deck_name.split("::", maxsplit=1)[0].replace('"', '\\"')
    combined_query = " OR ".join(note_queries)
    query = f'"deck:{root_deck_name_escaped}" AND ({combined_query})'

    return col.find_notes(query)
