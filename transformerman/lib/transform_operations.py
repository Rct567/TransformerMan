"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING, Callable, NamedTuple

from .field_updates import FieldUpdates

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import NoteId
    from .prompt_builder import PromptBuilder
    from .http_utils import LmProgressData
    from ..ui.field_widgets import FieldSelection
    from .transform_middleware import TransformMiddleware
    from .addon_config import AddonConfig
    from .lm_clients import LMClient
    from .selected_notes import SelectedNotes, SelectedNotesBatch, NoteModel


class TransformResults(NamedTuple):
    """Type definition for transformation results."""
    num_notes_updated: int
    num_notes_failed: int
    num_batches_requested: int
    num_batches_processed: int
    num_batches_success: int
    is_canceled: bool
    error: str | None


class CacheKey(NamedTuple):
    """Cache key for transformation results."""
    client_id: str
    note_type_name: str
    selected_fields: tuple[str, ...]
    writable_fields: tuple[str, ...]
    overwritable_fields: tuple[str, ...]
    note_ids: tuple[NoteId, ...]
    max_prompt_size: int
    field_instructions_hash: int


class NoteTransformer:
    """Transforms notes in batches (UI-agnostic)."""

    def __init__(  # noqa: PLR0913
        self,
        col: Collection,
        selected_notes: SelectedNotes,
        note_ids: Sequence[NoteId],
        lm_client: LMClient,
        prompt_builder: PromptBuilder,
        field_selection: FieldSelection,
        note_type: NoteModel,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """
        Initialize the NoteTransformer.

        Args:
            col: Anki collection.
            selected_notes: SelectedNotes instance.
            note_ids: Note IDs to transform.
            lm_client: LM client instance.
            prompt_builder: PromptBuilder instance.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            note_type: Note type of the notes.
            addon_config: Addon configuration.
            transform_middleware: Transform middleware instance.
        """
        self.col = col
        self.selected_notes = selected_notes
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.prompt_builder = prompt_builder
        self.field_selection = field_selection
        self.note_type = note_type
        self.addon_config = addon_config
        self.transform_middleware = transform_middleware
        self.logger = logging.getLogger(__name__)

        # Validate that we have notes with empty fields in writable_fields OR notes with overwritable_fields
        notes_to_transform = self.selected_notes.new_selected_notes(self.note_ids)
        has_empty_writable = notes_to_transform.has_note_with_empty_field(self.field_selection.writable)
        has_overwritable = bool(self.field_selection.overwritable)

        if not has_empty_writable and not has_overwritable:
            raise ValueError("No notes with empty writable fields found and no overwritable fields selected")

        # Filter to notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        filtered_notes = notes_to_transform.filter_by_writable_or_overwritable(
            self.field_selection.writable, self.field_selection.overwritable
        )

        # Update note_ids to filtered IDs
        self.note_ids = filtered_notes.get_ids()

        # Create batches based on prompt size
        self.batches = filtered_notes.batched_by_prompt_size(
            prompt_builder=self.prompt_builder,
            field_selection=self.field_selection,
            note_type=self.note_type,
            max_chars=self.addon_config.get_max_prompt_size(),
            max_examples=self.addon_config.get_max_examples(),
        )
        self.num_batches = len(self.batches)

    def _get_field_updates_for_batch(
        self,
        selected_notes_batch: SelectedNotesBatch,
        field_selection: FieldSelection,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[int, int, FieldUpdates, str | None]:
        """
        Get field updates for a single batch of notes using the provided LM client.

        Args:
            selected_notes_batch: Batch of notes to process.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            transform_middleware: Transform middleware instance.
            progress_callback: Optional callback for detailed progress.
            should_cancel: Optional callback to check if operation should be canceled.

        Returns:
            Tuple of (updated_count, failed_count, field_updates, error) for this batch.
            field_updates is a FieldUpdates instance mapping note_id -> dict of field_name -> new_value.
            error is None if no error, otherwise error message string.
        """

        # Build prompt
        self.prompt = self.prompt_builder.build_prompt(
            selected_notes_batch,
            self.note_type,
            field_selection,
            self.addon_config.get_max_examples(),
        )

        # Initial response
        self.response = None

        # Pre-transform middleware (e.g., log request)
        self.transform_middleware.before_transform(self)

        # Get LM response
        if not self.response:
            self.response = self.lm_client.transform(self.prompt, progress_callback=progress_callback, should_cancel=should_cancel)

        # Post-transform middleware (e.g., log response)
        self.transform_middleware.after_transform(self)

        #
        num_notes_updated = 0
        num_notes_failed = 0
        field_updates = FieldUpdates()
        error: str | None = None

        # Check for cancellation
        if self.response.is_canceled:
            return num_notes_updated, num_notes_failed, field_updates, None

        # Check for error in response
        if self.response.error is not None:
            error = self.response.error
            # Stop processing on first error
            return num_notes_updated, num_notes_failed, field_updates, error

        # Parse response
        response_field_updates = self.response.get_notes_from_xml()

        # Collect field updates
        for note in selected_notes_batch.get_notes():
            try:
                note_field_updates = response_field_updates.get(note.id, {})

                batch_field_updates: dict[str, str] = {}

                for field_name, content in note_field_updates.items():
                    # Collect if field is in writable fields and is empty
                    if field_name in self.field_selection.writable and not note[field_name].strip():
                        batch_field_updates[field_name] = content
                    # Also collect if field is in overwritable fields (regardless of content)
                    elif field_name in self.field_selection.overwritable:
                        batch_field_updates[field_name] = content

                if batch_field_updates:
                    # Store field updates for preview
                    field_updates.add_field_updates(note.id, batch_field_updates)
                    num_notes_updated += 1

            except Exception as e:
                self.logger.error(f"Error processing note {note.id} in preview: {e!r}")
                num_notes_failed += 1
                continue

        return num_notes_updated, num_notes_failed, field_updates, error

    def get_field_updates(
        self,
        progress_callback: Callable[[int, int, LmProgressData | None], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[TransformResults, FieldUpdates]:
        """
        Get field updates for notes in batches.

        Makes API calls to get field updates but does not apply them.

        Args:
            progress_callback: Optional callback for progress reporting.
                Called with (current_batch, total_batches, detailed_progress).
            should_cancel: Optional callback to check if operation should be canceled.
                Should return True if operation should be canceled.

        Returns:
            Tuple of (results, field_updates) where:
            - results: Transformation results dictionary, with is_canceled set if the operation was cancelled.
            - field_updates: FieldUpdates instance mapping note_id -> dict of field_name -> new_value
        """
        total_notes_updated = 0
        total_notes_failed = 0
        num_batches_processed = 0
        num_batches_success = 0
        batch_idx = 0
        all_field_updates = FieldUpdates()

        # Add overwritable fields to track globally
        for field_name in self.field_selection.overwritable:
            all_field_updates.add_overwritable_field(field_name)

        error: str | None = None
        is_canceled = False

        for batch_idx, selected_notes_batch in enumerate(self.batches):
            # Check if operation should be canceled
            if should_cancel and should_cancel():
                is_canceled = True
                break

            # Report progress
            if progress_callback:
                progress_callback(batch_idx, self.num_batches, None)

            def batch_progress_callback(data: LmProgressData, current_batch_idx: int = batch_idx) -> None:
                if progress_callback:
                    progress_callback(current_batch_idx, self.num_batches, data)

            # Get field updates for batch
            num_notes_updated, num_notes_failed, batch_field_updates, batch_error = self._get_field_updates_for_batch(
                selected_notes_batch,
                self.field_selection,
                progress_callback=batch_progress_callback,
                should_cancel=should_cancel,
            )

            if should_cancel and should_cancel():
                is_canceled = True
                break

            num_batches_processed += 1

            # Check for error in batch
            if batch_error is not None:
                error = batch_error
                # Stop processing on first error
                break

            total_notes_updated += num_notes_updated
            total_notes_failed += num_notes_failed
            all_field_updates.update(batch_field_updates)

            if len(batch_field_updates) < len(selected_notes_batch):
                num_fields_updates_missing = len(selected_notes_batch) - len(batch_field_updates)
                if not error:
                    error = (
                        f"{num_fields_updates_missing} field updates appear to be missing from the response "
                        f"(expected {len(selected_notes_batch)}, but got {len(batch_field_updates)})."
                    )
                    break

            num_batches_success += 1

        # Report completion
        if progress_callback:
            progress_callback(self.num_batches, self.num_batches, None)

        assert num_batches_success == self.num_batches or is_canceled or error

        results: TransformResults = TransformResults(
            num_notes_updated=total_notes_updated,
            num_notes_failed=total_notes_failed,
            num_batches_requested=self.num_batches,
            num_batches_processed=num_batches_processed,
            num_batches_success=num_batches_success,
            is_canceled=is_canceled,
            error=error,
        )

        return results, all_field_updates
