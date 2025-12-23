"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Any, NamedTuple

from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import QProgressDialog, QWidget, Qt
from aqt.utils import showInfo

from .prompt_builder import PromptBuilder
from .http_utils import LmRequestStage, LmProgressData
from .field_updates import FieldUpdates

if TYPE_CHECKING:
    from ..ui.field_widgets import FieldSelection

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from anki.collection import Collection, OpChanges
    from anki.notes import NoteId
    from .addon_config import AddonConfig
    from .lm_clients import LMClient, LmResponse
    from .selected_notes import SelectedNotes


class TransformResults(NamedTuple):
    """Type definition for transformation results."""
    num_notes_updated: int
    num_notes_failed: int
    num_batches_requested: int
    num_batches_processed: int
    num_batches_success: int
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


def create_lm_logger(addon_config: AddonConfig, user_files_dir: Path) -> tuple[Callable[[str], None], Callable[[LmResponse], None]]:
    """Create logging functions for LM requests and responses."""
    logs_dir = user_files_dir / "logs"

    log_requests_enabled = addon_config.is_enabled("log_lm_requests", False)
    log_responses_enabled = addon_config.is_enabled("log_lm_responses", False)

    if log_requests_enabled or log_responses_enabled:
        logs_dir.mkdir(parents=True, exist_ok=True)

    def log_request(prompt: str) -> None:
        if log_requests_enabled:
            requests_file = logs_dir / "lm_requests.log"
            timestamp = datetime.now().isoformat()
            with requests_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {prompt}\n\n")

    def log_response(response: LmResponse) -> None:
        if log_responses_enabled:
            responses_file = logs_dir / "lm_responses.log"
            timestamp = datetime.now().isoformat()
            with responses_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {response.text_response}\n\n")

    return log_request, log_response


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
        user_files_dir: Path,
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
            user_files_dir: Directory for user files.
        """
        self.col = col
        self.selected_notes = selected_notes
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.prompt_builder = prompt_builder
        self.field_selection = field_selection
        self.note_type_name = note_type_name
        self.addon_config = addon_config
        self.user_files_dir = user_files_dir
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
        log_request: Callable[[str], None],
        log_response: Callable[[LmResponse], None],
        progress_callback: Callable[[LmProgressData], None] | None = None,
    ) -> tuple[int, int, FieldUpdates, str | None]:
        """
        Get field updates for a single batch of notes (preview mode).

        Args:
            batch_selected_notes: Batch of notes to process.
            log_request: Function to log LM requests.
            log_response: Function to log LM responses.
            progress_callback: Optional callback for detailed progress.

        Returns:
            Tuple of (updated_count, failed_count, field_updates, error) for this batch.
            field_updates is a FieldUpdates instance mapping note_id -> dict of field_name -> new_value.
            error is None if no error, otherwise error message string.
        """
        num_notes_updated = 0
        num_notes_failed = 0
        field_updates = FieldUpdates()
        error: str | None = None

        try:
            # Build prompt
            prompt = self.prompt_builder.build_prompt(
                batch_selected_notes,
                field_selection,
                self.addon_config.get_max_examples(),
                self.note_type_name,
            )

            # Log request
            log_request(prompt)

            # Get LM response
            response = self.lm_client.transform(prompt, progress_callback=progress_callback)

            # Log response
            log_response(response)

            # Check for error in response
            if response.error is not None:
                error = response.error
                # Stop processing on first error
                return num_notes_updated, num_notes_failed, field_updates, error

            # Parse response
            response_field_updates = response.get_notes_from_xml()

            # Collect field updates (preview mode)
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

        except Exception as e:
            self.logger.error(f"Error processing batch in preview: {e!r}")
            num_notes_failed += len(batch_selected_notes)

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
            - results: Transformation results dictionary
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

        log_request, log_response = create_lm_logger(self.addon_config, self.user_files_dir)

        for batch_idx, batch_selected_notes in enumerate(self.batches):
            # Check if operation should be canceled
            if should_cancel and should_cancel():
                break

            # Report progress
            if progress_callback:
                progress_callback(batch_idx, self.num_batches, None)

            def batch_progress_callback(data: LmProgressData, current_batch_idx: int = batch_idx) -> None:
                if progress_callback:
                    progress_callback(current_batch_idx, self.num_batches, data)

            # Get field updates for batch (preview mode)
            num_notes_updated, num_notes_failed, batch_field_updates, batch_error = self._get_field_updates_for_batch(
                batch_selected_notes, self.field_selection, log_request, log_response, progress_callback=batch_progress_callback
            )

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

        assert error is None or num_batches_success < self.num_batches

        results: TransformResults = TransformResults(
            num_notes_updated=total_notes_updated,
            num_notes_failed=total_notes_failed,
            num_batches_requested=self.num_batches,
            num_batches_processed=num_batches_processed,
            num_batches_success=num_batches_success,
            error=error,
        )

        return results, all_field_updates


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
        user_files_dir: Path,
    ) -> None:
        """
        Initialize the transformer.

        Args:
            parent: Parent widget for dialogs.
            col: Anki collection.
            selected_notes: SelectedNotes instance.
            lm_client: LM client instance.
            addon_config: Addon configuration instance.
            user_files_dir: Directory for user files.
        """
        self.parent = parent
        self.col = col
        self.selected_notes = selected_notes
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.user_files_dir = user_files_dir
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
            user_files_dir=self.user_files_dir,
        )

        # Create progress dialog
        # Use indeterminate/busy indicator for single batch, regular progress bar for multiple batches
        if transformer.num_batches == 1:
            # Indeterminate progress (busy indicator) - range (0, 0) creates infinite progress bar
            progress = QProgressDialog(
                "Processing...",
                "Cancel",
                0,
                0,
                self.parent,
            )
        else:
            # Regular progress bar with defined range
            progress = QProgressDialog(
                f"Processing batch 0 of {transformer.num_batches}...",
                "Cancel",
                0,
                transformer.num_batches,
                self.parent,
            )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)  # Show immediately
        progress.setMinimumWidth(300)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        cancel_requested = False

        def on_cancel() -> None:
            nonlocal cancel_requested
            cancel_requested = True
            # progress.setLabelText("Canceling... please wait for current batch to finish.")
            progress.setCancelButtonText(None)  # Hide cancel button

        # Disconnect default canceled slot to prevent immediate closing
        try:
            progress.canceled.disconnect()
        except TypeError:
            pass
        progress.canceled.connect(on_cancel)

        progress.show()

        is_dialog_active = True

        def process_batches(_: Collection) -> tuple[TransformResults, FieldUpdates]:
            """Background operation that processes each batch."""

            # Create callbacks for progress and cancellation
            def progress_callback(current: int, total: int, detailed: LmProgressData | None = None) -> None:
                def get_detailed_message(data: LmProgressData) -> str:
                    """Format detailed progress message for sending/receiving stages."""
                    if data.stage == LmRequestStage.SENDING:
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

                def update_ui() -> None:
                    if not is_dialog_active:
                        return

                    try:
                        # Determine prefix based on batch count
                        prefix = "Processing..." if total == 1 else f"Processing batch {current + 1} of {total}..."

                        # Build message
                        if detailed:
                            msg = get_detailed_message(detailed)
                            progress.setLabelText(f"{prefix}\n{msg}")
                        else:
                            progress.setLabelText(prefix)

                        # Only update value for multiple batches (single batch uses indeterminate mode)
                        if total > 1:
                            progress.setValue(current)
                    except RuntimeError:
                        # Progress dialog already deleted
                        pass

                mw.taskman.run_on_main(update_ui)

            def should_cancel() -> bool:
                return cancel_requested

            # Run transformation with callbacks (always returns field updates)
            return transformer.get_field_updates(
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )

        def on_success_callback(result_tuple: tuple[TransformResults, FieldUpdates]) -> None:
            """Called when transformation succeeds."""
            nonlocal is_dialog_active
            is_dialog_active = False
            try:
                progress.close()
            except RuntimeError:
                pass

            # if cancel_requested:
            #     return

            results, field_updates = result_tuple
            # Cache the results
            if results.error is None and (results.num_batches_success > 0 or len(field_updates) > 0):
                self._cache[cache_key] = (results, field_updates)

            # Call the success callback
            on_success(results, field_updates)

        def on_failure(exc: Exception) -> None:
            """Called when operation fails."""
            nonlocal is_dialog_active
            is_dialog_active = False
            try:
                progress.close()
            except RuntimeError:
                pass
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
