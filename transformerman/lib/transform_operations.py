"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Callable, Any, NamedTuple

from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import QProgressDialog, QTimer, QWidget, Qt
from aqt.utils import showInfo

from .prompt_builder import PromptBuilder
from .http_utils import LmRequestStage, LmProgressData
from .field_updates import FieldUpdates

if TYPE_CHECKING:
    from ..ui.field_widgets import FieldSelection
    from .transform_middleware import TransformMiddleware
    from collections.abc import Sequence
    from anki.collection import Collection, OpChanges
    from anki.notes import NoteId
    from .addon_config import AddonConfig
    from .lm_clients import LMClient
    from .selected_notes import SelectedNotes


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
        note_type_name: str,
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
            note_type_name: Name of note type.
            addon_config: Addon configuration.
            transform_middleware: Transform middleware instance.
        """
        self.col = col
        self.selected_notes = selected_notes
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.prompt_builder = prompt_builder
        self.field_selection = field_selection
        self.note_type_name = note_type_name
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
            note_type_name=self.note_type_name,
            max_chars=self.addon_config.get_max_prompt_size(),
            max_examples=self.addon_config.get_max_examples(),
        )
        self.num_batches = len(self.batches)

    def _get_field_updates_for_batch(
        self,
        batch_selected_notes: SelectedNotes,
        field_selection: FieldSelection,
        transform_middleware: TransformMiddleware,
        progress_callback: Callable[[LmProgressData], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[int, int, FieldUpdates, str | None]:
        """
        Get field updates for a single batch of notes using the provided LM client.

        Args:
            batch_selected_notes: Batch of notes to process.
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
        prompt = self.prompt_builder.build_prompt(
            batch_selected_notes,
            field_selection,
            self.addon_config.get_max_examples(),
            self.note_type_name,
        )

        # Initial response
        self.response = None

        # Pre-transform middleware (e.g., log request)
        transform_middleware.before_transform(prompt, self)

        # Get LM response
        if not self.response:
            self.response = self.lm_client.transform(prompt, progress_callback=progress_callback, should_cancel=should_cancel)

        # Post-transform middleware (e.g., log response)
        transform_middleware.after_transform(self)

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
        for note in batch_selected_notes.get_notes():
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
        all_field_updates = FieldUpdates(selected_notes=self.selected_notes)

        # Add overwritable fields to track globally
        for field_name in self.field_selection.overwritable:
            all_field_updates.add_overwritable_field(field_name)

        error: str | None = None
        is_canceled = False

        for batch_idx, batch_selected_notes in enumerate(self.batches):
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
                batch_selected_notes,
                self.field_selection,
                self.transform_middleware,
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

            if len(batch_field_updates) < len(batch_selected_notes):
                num_fields_updates_missing = len(batch_selected_notes) - len(batch_field_updates)
                if not error:
                    error = (
                        f"{num_fields_updates_missing} field updates appear to be missing from the response "
                        f"(expected {len(batch_selected_notes)}, but got {len(batch_field_updates)})."
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


class TransformProgressDialog(QProgressDialog):
    """
    Custom progress dialog for transformation operations with intelligent wait messaging.

    Automatically switches from "Sending request..." to "Waiting for response... Xs"
    after a configurable threshold when the LM takes time to respond.
    """

    WAIT_THRESHOLD_SECONDS = 3

    def __init__(self, num_batches: int, parent: QWidget | None = None):
        """
        Initialize the progress dialog.

        Args:
            num_batches: Number of batches to process.
            parent: Parent widget.
        """
        # Use indeterminate/busy indicator for single batch, regular progress bar for multiple
        if num_batches == 1:
            super().__init__("Processing...", "Cancel", 0, 0, parent)
        else:
            super().__init__(f"Processing batch 0 of {num_batches}...", "Cancel", 0, num_batches, parent)

        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumDuration(0)
        self.setMinimumWidth(300)
        self.setAutoClose(False)
        self.setAutoReset(False)

        self._is_active = True
        self._cancel_requested = False
        self._current_stage: LmRequestStage | None = None
        self._sending_start_time: float | None = None

        # Timer for updating wait counter
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_wait_counter)
        self._timer.start(1000)

        # Connect cancel signal
        self.canceled.disconnect()
        self.canceled.connect(self._on_cancel)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self._cancel_requested = True
        self._timer.stop()
        self.setCancelButtonText(None)

    def is_cancel_requested(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_requested

    def update_progress(self, current_batch: int, total_batches: int, detailed: LmProgressData | None = None) -> None:
        """
        Update progress display with batch and detailed information.

        Args:
            current_batch: Current batch index (0-based).
            total_batches: Total number of batches.
            detailed: Optional detailed progress data from LM client.
        """
        if not self._is_active:
            return

        if detailed:
            if detailed.stage == LmRequestStage.RECEIVING:
                self._sending_start_time = None

        try:
            # Track stage and timing
            if detailed:
                if detailed.stage == LmRequestStage.SENDING and self._sending_start_time is None:
                    self._sending_start_time = time.time()
                self._current_stage = detailed.stage

            # Build progress message
            progress_msg: list[str] = []

            if self._cancel_requested:
                progress_msg.append("Processing canceled...")
            else:
                if total_batches == 1:
                    progress_msg.append("Processing...")
                else:
                    progress_msg.append(f"Processing batch {current_batch + 1} of {total_batches}...")

            if detailed:
                detailed_msg = self._format_detailed_message(detailed)
                progress_msg.append(detailed_msg)

            self.setLabelText("\n".join(progress_msg))

            # Update progress value for multiple batches
            if total_batches > 1:
                self.setValue(current_batch)
        except RuntimeError:
            # Dialog already deleted
            pass

    def _format_detailed_message(self, data: LmProgressData) -> str:
        """
        Format detailed progress message for sending/receiving stages.

        Args:
            data: Progress data from LM client.

        Returns:
            Formatted message string.
        """
        if data.stage == LmRequestStage.SENDING:
            if self._should_show_wait_message():
                wait_seconds = self._get_wait_seconds()
                return f"Waiting for response... {wait_seconds}s"
            return "Sending request..."

        # RECEIVING stage
        size_kb = data.total_bytes / 1024
        speed_kb_s = (data.total_bytes / data.elapsed) / 1024 if data.elapsed > 0 else 0

        if not data.text_chunk:  # Download phase (non-SSE or before first chunk)
            if data.content_length:
                total_kb = data.content_length / 1024
                return f"Receiving response... ({size_kb:.0f} KB / {total_kb:.0f} KB at {speed_kb_s:.0f} KB/s)"
            return f"Receiving response... ({size_kb:.0f} KB at {speed_kb_s:.0f} KB/s)"

        # Streaming phase
        return f"Processing response... ({size_kb:.0f} KB at {speed_kb_s:.0f} KB/s)"

    def _should_show_wait_message(self) -> bool:
        """Determine if we should show the waiting message."""
        return (
            self._current_stage == LmRequestStage.SENDING
            and self._sending_start_time is not None
            and time.time() - self._sending_start_time > self.WAIT_THRESHOLD_SECONDS
        )

    def _get_wait_seconds(self) -> int:
        """Calculate seconds spent waiting beyond the threshold."""
        if not self._sending_start_time:
            return 0
        elapsed = time.time() - self._sending_start_time
        return max(0, int(elapsed - self.WAIT_THRESHOLD_SECONDS))

    def _update_wait_counter(self) -> None:
        """Update the wait counter in the progress label (called by timer)."""
        if not self._should_show_wait_message():
            return

        current_text = self.labelText()
        wait_seconds = self._get_wait_seconds()

        if "Waiting for response..." in current_text:
            # Update the existing counter
            new_text = re.sub(r"Waiting for response\.\.\. \d+s", f"Waiting for response... {wait_seconds}s", current_text)
            self.setLabelText(new_text)
        elif "Sending request..." in current_text:
            # Switch from sending to waiting
            new_text = current_text.replace("Sending request...", f"Waiting for response... {wait_seconds}s")
            self.setLabelText(new_text)

    def cleanup(self) -> None:
        """Clean up resources and close the dialog."""
        self._is_active = False
        self._timer.stop()
        try:
            self.close()
        except RuntimeError:
            pass


class TransformNotesWithProgress:
    """
    Manages note transformation with progress tracking and caching.

    This class provides a stateful interface for transforming notes, including:

    - Progress tracking during transformation
    - Caching of transformation results
    - API call estimation
    - Field update application
    """

    _cache: dict[CacheKey, tuple[TransformResults, FieldUpdates]]

    def __init__(
        self,
        parent: QWidget,
        col: Collection,
        selected_notes: SelectedNotes,
        lm_client: LMClient,
        addon_config: AddonConfig,
        transform_middleware: TransformMiddleware,
    ) -> None:
        """
        Initialize the transformer.

        Args:
            parent: Parent widget for dialogs.
            col: Anki collection.
            selected_notes: SelectedNotes instance.
            lm_client: LM client instance.
            addon_config: Addon configuration instance.
            transform_middleware: Transform middleware instance.
        """
        self.parent = parent
        self.col = col
        self.selected_notes = selected_notes
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.transform_middleware = transform_middleware
        self.logger = logging.getLogger(__name__)
        self._prompt_builder = PromptBuilder(col)

        # Cache for transformation results
        self._cache = {}

    def _get_cache_key(
        self,
        note_type_name: str,
        field_selection: FieldSelection,
        note_ids: Sequence[NoteId],
    ) -> CacheKey:
        """Generate a cache key for the given transformation parameters."""
        # Create a hash of field_instructions for cache key
        # Sort items to ensure consistent hash for same instructions
        field_instructions_items = sorted(self._prompt_builder.field_instructions.items())
        field_instructions_hash = hash(tuple(field_instructions_items))

        return CacheKey(
            client_id=self.lm_client.id,
            note_type_name=note_type_name,
            selected_fields=tuple(field_selection.selected),
            writable_fields=tuple(field_selection.writable),
            overwritable_fields=tuple(field_selection.overwritable),
            note_ids=tuple(note_ids),
            max_prompt_size=self.addon_config.get_max_prompt_size(),
            field_instructions_hash=field_instructions_hash,
        )

    def is_cached(
        self,
        note_type_name: str,
        field_selection: FieldSelection,
        note_ids: Sequence[NoteId],
    ) -> bool:
        """
        Check if transformation results are cached.

        Args:
            note_type_name: Name of the note type.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            note_ids: List of note IDs to transform.

        Returns:
            True if results are cached, False otherwise.
        """
        cache_key = self._get_cache_key(note_type_name, field_selection, note_ids)
        return cache_key in self._cache

    def get_num_api_calls_needed(
        self,
        note_type_name: str,
        field_selection: FieldSelection,
        note_ids: Sequence[NoteId],
    ) -> int:
        """
        Calculate the number of API calls needed for the given parameters.
        If results are already cached, returns 0. Otherwise, calculates based on
        actual prompt batching.

        Args:
            note_type_name: Name of the note type.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            note_ids: List of note IDs to transform.

        Returns:
            Number of API calls needed.
        """
        # If cached, no API calls needed
        if self.is_cached(note_type_name, field_selection, note_ids):
            return 0

        if not field_selection.writable and not field_selection.overwritable:
            return 0

        # Filter by note type first - filter_by_note_type returns a list of NoteIds
        filtered_note_ids_by_type = self.selected_notes.filter_by_note_type(note_type_name)

        # Intersect with provided note_ids
        filtered_note_ids = [nid for nid in note_ids if nid in filtered_note_ids_by_type]

        if not filtered_note_ids:
            return 0

        # Get notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        notes_with_fields = self.selected_notes.new_selected_notes(filtered_note_ids).filter_by_writable_or_overwritable(
            field_selection.writable, field_selection.overwritable
        )

        if not notes_with_fields:
            return 0

        # Calculate actual batches
        batches = notes_with_fields.batched_by_prompt_size(
            prompt_builder=self._prompt_builder,
            field_selection=field_selection,
            note_type_name=note_type_name,
            max_chars=self.addon_config.get_max_prompt_size(),
            max_examples=self.addon_config.get_max_examples(),
        )

        return len(batches)

    def transform(
        self,
        note_ids: Sequence[NoteId],
        note_type_name: str,
        field_selection: FieldSelection,
        on_success: Callable[[TransformResults, FieldUpdates], None],
    ) -> None:
        """
        Transform notes in batches with progress tracking.

        Makes API calls to get field updates and returns them via the on_success callback.
        Results are cached for future calls with the same parameters.

        Args:
            note_ids: List of note IDs to transform.
            note_type_name: Name of the note type.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            on_success: Callback for transformation success.
                Called with (results, field_updates) when transformation completes successfully.
        """
        # Check cache first
        cache_key = self._get_cache_key(note_type_name, field_selection, note_ids)
        if cache_key in self._cache:
            results, field_updates = self._cache[cache_key]
            on_success(results, field_updates)
            return

        # Create NoteTransformer (UI-agnostic)
        transformer = NoteTransformer(
            col=self.col,
            selected_notes=self.selected_notes,
            note_ids=note_ids,
            lm_client=self.lm_client,
            prompt_builder=self._prompt_builder,
            field_selection=field_selection,
            note_type_name=note_type_name,
            addon_config=self.addon_config,
            transform_middleware=self.transform_middleware,
        )

        # Create custom progress dialog
        progress = TransformProgressDialog(transformer.num_batches, self.parent)
        progress.show()

        def process_batches(_: Collection) -> tuple[TransformResults, FieldUpdates]:
            """Background operation that processes each batch."""

            # Create callbacks for progress and cancellation
            def progress_callback(current: int, total: int, detailed: LmProgressData | None = None) -> None:
                def update_ui() -> None:
                    progress.update_progress(current, total, detailed)

                mw.taskman.run_on_main(update_ui)

            def should_cancel() -> bool:
                return progress.is_cancel_requested()

            # Run transformation with callbacks (always returns field updates)
            results, field_updates = transformer.get_field_updates(
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )
            return results, field_updates

        def on_success_callback(result_tuple: tuple[TransformResults, FieldUpdates]) -> None:
            """Called when transformation succeeds."""
            progress.cleanup()

            results, field_updates = result_tuple
            # Cache the results
            if results.error is None and not results.is_canceled and (results.num_batches_success > 0 or len(field_updates) > 0):
                self._cache[cache_key] = (results, field_updates)

            # Call the success callback
            on_success(results, field_updates)

        def on_failure(exc: Exception) -> None:
            """Called when operation fails."""
            progress.cleanup()
            showInfo(f"Error during transformation: {exc!s}", parent=self.parent)

        # Run the operation in the background
        QueryOp(
            parent=self.parent,
            op=process_batches,
            success=on_success_callback,
        ).without_collection().failure(on_failure).run_in_background()

    def apply_field_updates(
        self,
        field_updates: FieldUpdates,
        on_success: Callable[[dict[str, int]], None] | None = None,
        on_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        Apply stored field updates to the Anki collection.

        Args:
            field_updates: FieldUpdates mapping note_id -> dict of field_name -> new_value.
            on_success: Callback called with results dict when operation succeeds.
            on_failure: Callback called with exception when operation fails.
        """
        apply_field_updates_with_operation(
            parent=self.parent,
            col=self.col,
            field_updates=field_updates,
            logger=self.logger,
            on_success=on_success,
            on_failure=on_failure,
        )

    def update_field_instructions(self, field_instructions: dict[str, str]) -> None:
        """Update the field instructions for the transformer."""
        self._prompt_builder.update_field_instructions(field_instructions)


def apply_field_updates_with_operation(
    parent: QWidget,
    col: Collection,
    field_updates: FieldUpdates,
    logger: logging.Logger,
    on_success: Callable[[dict[str, int]], None] | None = None,
    on_failure: Callable[[Exception], None] | None = None,
) -> None:
    """
    Apply stored field updates to the Anki collection using update_notes operation.

    Args:
        parent: Parent widget for the operation.
        col: Anki collection.
        field_updates: FieldUpdates mapping note_id -> dict of field_name -> new_value.
        logger: Logger instance.
        on_success: Callback called with results dict when operation succeeds.
        on_failure: Callback called with exception when operation fails.
    """
    # Collect notes that need updating
    notes_to_update = []
    failed = 0
    field_updates.is_applied = True

    for note_id, updates in field_updates.items():
        try:
            note = col.get_note(note_id)
            note_updated = False

            for field_name, content in updates.items():
                if field_name in note:
                    note[field_name] = content
                    note_updated = True

            if note_updated:
                notes_to_update.append(note)
        except Exception as e:
            logger.error(f"Error preparing note {note_id} for update: {e!r}")
            failed += 1

    if not notes_to_update:
        # No notes to update, call on_success immediately
        if on_success:
            on_success({"updated": 0, "failed": failed})
        return

    def on_op_success(_: Any) -> None:
        """Called when update notes operation succeeds."""
        if on_success:
            on_success({"updated": len(notes_to_update), "failed": failed})

    def on_op_failure(exception: Exception) -> None:
        """Called when update notes operation fails."""
        logger.error(f"Error in update notes operation: {exception!r}")
        if on_failure:
            on_failure(exception)

    def transform_operation(col: Collection) -> OpChanges:
        """Update notes and create undo entry."""
        pos = col.add_custom_undo_entry("Transforming fields")
        col.update_notes(notes_to_update)
        return col.merge_undo_entries(pos)

    # Run the operation
    CollectionOp(parent, op=transform_operation).success(on_op_success).failure(on_op_failure).run_in_background()
