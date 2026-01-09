"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING, Callable, NamedTuple

from .response_middleware import PromptProcessor

from .field_updates import FieldUpdates

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import NoteId
    from .transform_prompt_builder import TransformPromptBuilder
    from .http_utils import LmProgressData
    from ..ui.transform.field_widgets import FieldSelection
    from .response_middleware import ResponseMiddleware
    from .addon_config import AddonConfig
    from .lm_clients import LMClient
    from .selected_notes import SelectedNotesBatch, SelectedNotesFromType


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
    max_notes_per_batch: int
    field_instructions_hash: int


class NoteTransformer(PromptProcessor):
    """Transforms notes in batches (UI-agnostic)."""

    target_notes: SelectedNotesFromType
    batches: Sequence[SelectedNotesBatch]

    def __init__(
        self,
        col: Collection,
        selected_notes: SelectedNotesFromType,
        lm_client: LMClient,
        prompt_builder: TransformPromptBuilder,
        field_selection: FieldSelection,
        addon_config: AddonConfig,
        middleware: ResponseMiddleware,
        prompt_interceptor: Callable[[str], str] | None = None,
    ) -> None:
        """
        Initialize the NoteTransformer.

        Args:
            col: Anki collection.
            selected_notes: Selected notes to transform (only those who match the criteria set by field_selection).
            lm_client: LM client instance.
            prompt_builder: PromptBuilder instance.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            addon_config: Addon configuration.
            middleware: Middleware to use for processing responses.
            prompt_interceptor: Optional function to intercept and modify the prompt template before use.
        """
        self.col = col
        self.selected_notes = selected_notes
        self.lm_client = lm_client
        self.prompt_builder = prompt_builder
        self.field_selection = field_selection
        self.addon_config = addon_config
        self.middleware = middleware
        self.logger = logging.getLogger(__name__)

        # Validate that we have notes with empty fields in writable_fields OR notes with overwritable_fields
        notes_to_transform = self.selected_notes
        has_empty_writable = notes_to_transform.has_note_with_empty_field(self.field_selection.writable)
        has_overwritable = bool(self.field_selection.overwritable)

        if not has_empty_writable and not has_overwritable:
            raise ValueError("No notes with empty writable fields found and no overwritable fields selected")

        # Filter to notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        self.target_notes = notes_to_transform.filter_by_writable_or_overwritable(
            self.field_selection.writable, self.field_selection.overwritable
        )

        # Generate initial template
        self.prompt_template = self.prompt_builder.build_prompt_template(
            self.target_notes,
            self.field_selection,
            self.addon_config.get_max_examples(),
        )

        # Apply interceptor if provided
        if prompt_interceptor:
            self.prompt_template = prompt_interceptor(self.prompt_template)

        # Create batches based on prompt size
        self.batches = self.target_notes.batched_by_prompt_size(
            prompt_builder=self.prompt_builder,
            field_selection=self.field_selection,
            max_chars=self.addon_config.get_max_prompt_size(),
            max_notes_per_batch=self.addon_config.get_max_notes_per_batch(),
            max_examples=self.addon_config.get_max_examples(),
            prompt_template=self.prompt_template,
        )
        self.num_batches = len(self.batches)

    def _get_field_updates_for_batch(
        self,
        render_prompt: Callable[[SelectedNotesBatch], str],
        selected_notes_batch: SelectedNotesBatch,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[int, int, FieldUpdates, str | None]:
        """
        Get field updates for a single batch of notes using the provided LM client.

        Args:
            render_prompt: Function to render the prompt for the given batch.
            selected_notes_batch: Batch of notes to process.
            progress_callback: Optional callback for detailed progress.
            should_cancel: Optional callback to check if operation should be canceled.

        Returns:
            Tuple of (updated_count, failed_count, field_updates, error) for this batch.
            field_updates is a FieldUpdates instance mapping note_id -> dict of field_name -> new_value.
            error is None if no error, otherwise error message string.
        """

        # Build prompt
        self.prompt = render_prompt(selected_notes_batch)

        # Initial response
        self.response = None

        # Pre-response hook for middleware
        self.middleware.before_response(self)

        # Get LM response
        if not self.response:
            self.response = self.lm_client.process_prompt(self.prompt, progress_callback=progress_callback, should_cancel=should_cancel)

        # Post-response hook for middleware
        self.middleware.after_response(self)

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

        # Prompt builder
        render_prompt = self.prompt_builder.get_renderer_from_template(
            self.prompt_template,
            self.target_notes,
            self.field_selection,
        )

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
                render_prompt,
                selected_notes_batch,
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
