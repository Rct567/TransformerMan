"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, TypedDict, Any

from aqt import mw
from aqt.operations import QueryOp, CollectionOp
from aqt.utils import showInfo
from aqt.qt import QProgressDialog, QWidget, Qt

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from anki.collection import Collection
    from anki.notes import NoteId
    from .addon_config import AddonConfig
    from .lm_clients import LMClient, LmResponse
    from .prompt_builder import PromptBuilder
    from .selected_notes import SelectedNotes


class TransformResults(TypedDict):
    """Type definition for transformation results."""
    updated: int
    failed: int
    batches_processed: int
    error: str | None


def create_lm_logger(addon_config: AddonConfig, user_files_dir: Path) -> tuple[Callable[[str], None], Callable[[LmResponse], None]]:
    """Create logging functions for LM requests and responses."""
    logs_dir = user_files_dir / 'logs'

    log_requests_enabled = addon_config.is_enabled("log_lm_requests", False)
    log_responses_enabled = addon_config.is_enabled("log_lm_responses", False)

    if log_requests_enabled or log_responses_enabled:
        logs_dir.mkdir(parents=True, exist_ok=True)

    def log_request(prompt: str) -> None:
        if log_requests_enabled:
            requests_file = logs_dir / 'lm_requests.log'
            timestamp = datetime.now().isoformat()
            with requests_file.open('a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {prompt}\n\n")

    def log_response(response: LmResponse) -> None:
        if log_responses_enabled:
            responses_file = logs_dir / 'lm_responses.log'
            timestamp = datetime.now().isoformat()
            with responses_file.open('a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {response.text_response}\n\n")

    return log_request, log_response


class NoteTransformer:
    """Transforms notes in batches."""

    def __init__(  # noqa: PLR0913
        self,
        col: Collection,
        selected_notes: SelectedNotes,
        note_ids: Sequence[NoteId],
        lm_client: LMClient,
        prompt_builder: PromptBuilder,
        selected_fields: Sequence[str],
        note_type_name: str,
        batch_size: int,
        addon_config: AddonConfig,
        user_files_dir: Path,
    ) -> None:
        """
        Initialize the NoteTransformer.

        Args:
            col: Anki collection.
            selected_notes: SelectedNotes instance.
            note_ids: List of note IDs to transform.
            lm_client: LM client instance.
            prompt_builder: Prompt builder instance.
            selected_fields: Sequence of field names to fill.
            note_type_name: Name of the note type.
            batch_size: Number of notes per batch.
            addon_config: Addon configuration instance.
            user_files_dir: Directory for user files.
        """
        self.col = col
        self.selected_notes = selected_notes
        self.note_ids = note_ids
        self.lm_client = lm_client
        self.prompt_builder = prompt_builder
        self.selected_fields = selected_fields
        self.note_type_name = note_type_name
        self.batch_size = batch_size
        self.addon_config = addon_config
        self.user_files_dir = user_files_dir
        self.logger = logging.getLogger(__name__)

        # Validate that we have notes with empty fields
        notes_to_transform = self.selected_notes.get_selected_notes(self.note_ids)
        if not notes_to_transform.has_note_with_empty_field(self.selected_fields):
            raise ValueError("No notes with empty fields found")

        # Filter to only notes with empty fields
        notes_to_transform = notes_to_transform.filter_by_empty_field(self.selected_fields)
        # Update note_ids to filtered IDs
        self.note_ids = notes_to_transform.note_ids

        # Create batches
        self.batches = notes_to_transform.batched(self.batch_size)
        self.num_batches = len(self.batches)

    def _get_field_updates_for_batch(
        self,
        batch_selected_notes: SelectedNotes,
        log_request: Callable[[str], None],
        log_response: Callable[[LmResponse], None],
    ) -> tuple[int, int, dict[NoteId, dict[str, str]], str | None]:
        """
        Get field updates for a single batch of notes (preview mode).

        Args:
            batch_selected_notes: Batch of notes to process.
            log_request: Function to log LM requests.
            log_response: Function to log LM responses.

        Returns:
            Tuple of (updated_count, failed_count, field_updates, error) for this batch.
            field_updates is a dict mapping note_id -> dict of field_name -> new_value.
            error is None if no error, otherwise error message string.
        """
        updated = 0
        failed = 0
        field_updates_dict: dict[NoteId, dict[str, str]] = {}
        error: str | None = None

        try:
            # Build prompt
            prompt = self.prompt_builder.build_prompt(
                self.col, batch_selected_notes, self.selected_fields, self.note_type_name
            )

            # Log request
            log_request(prompt)

            # Get LM response
            response = self.lm_client.transform(prompt)

            # Log response
            log_response(response)

            # Check for error in response
            if response.error is not None:
                error = response.error
                # Stop processing on first error
                return updated, failed, field_updates_dict, error

            # Parse response
            field_updates = response.get_notes_from_xml()

            # Collect field updates (preview mode)
            for nid in batch_selected_notes.note_ids:
                try:
                    note = self.col.get_note(nid)
                    updates = field_updates.get(nid, {})

                    batch_field_updates: dict[str, str] = {}

                    for field_name, content in updates.items():
                        # Only collect if field is in selected fields and is empty
                        if field_name in self.selected_fields and not note[field_name].strip():
                            batch_field_updates[field_name] = content

                    if batch_field_updates:
                        # Store field updates for preview
                        field_updates_dict[nid] = batch_field_updates
                        updated += 1

                except Exception as e:
                    self.logger.error(f"Error processing note {nid} in preview: {e!r}")
                    failed += 1
                    continue

        except Exception as e:
            self.logger.error(f"Error processing batch in preview: {e!r}")
            failed += len(batch_selected_notes.note_ids)

        return updated, failed, field_updates_dict, error


    def get_field_updates(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[TransformResults, dict[NoteId, dict[str, str]]]:
        """
        Get field updates for notes in batches.

        Makes API calls to get field updates but does not apply them.

        Args:
            progress_callback: Optional callback for progress reporting.
                Called with (current_batch, total_batches).
            should_cancel: Optional callback to check if operation should be canceled.
                Should return True if operation should be canceled.

        Returns:
            Tuple of (results, field_updates) where:
            - results: Transformation results dictionary
            - field_updates: dict mapping note_id -> dict of field_name -> new_value
        """
        total_updated = 0
        total_failed = 0
        batch_idx = 0
        all_field_updates: dict[NoteId, dict[str, str]] = {}
        error: str | None = None

        log_request, log_response = create_lm_logger(self.addon_config, self.user_files_dir)

        for batch_idx, batch_selected_notes in enumerate(self.batches):
            # Check if operation should be canceled
            if should_cancel and should_cancel():
                break

            # Report progress
            if progress_callback:
                progress_callback(batch_idx, self.num_batches)

            # Get field updates for batch (preview mode)
            num_updated, num_failed, batch_field_updates, batch_error = self._get_field_updates_for_batch(
                batch_selected_notes, log_request, log_response
            )

            # Check for error in batch
            if batch_error is not None:
                error = batch_error
                # Stop processing on first error
                break

            total_updated += num_updated
            total_failed += num_failed
            all_field_updates.update(batch_field_updates)

        # Report completion
        if progress_callback:
            progress_callback(self.num_batches, self.num_batches)

        results: TransformResults = {
            "updated": total_updated,
            "failed": total_failed,
            "batches_processed": batch_idx + 1 if not (should_cancel and should_cancel()) else batch_idx,
            "error": error,
        }

        return results, all_field_updates



def transform_notes_with_progress(  # noqa: PLR0913
    parent: QWidget,
    col: Collection,
    selected_notes: SelectedNotes,
    note_ids: Sequence[NoteId],
    lm_client: LMClient,
    prompt_builder: PromptBuilder,
    selected_fields: Sequence[str],
    note_type_name: str,
    batch_size: int,
    addon_config: AddonConfig,
    user_files_dir: Path,
    on_success: Callable[[TransformResults, dict[NoteId, dict[str, str]]], None],
) -> None:
    """
    Transform notes in batches with progress tracking.

    Makes API calls to get field updates and returns them.
    The UI decides whether to show preview or apply updates.

    Args:
        parent: Parent widget for dialogs.
        col: Anki collection.
        selected_notes: SelectedNotes instance.
        note_ids: List of note IDs to transform.
        lm_client: LM client instance.
        prompt_builder: Prompt builder instance.
        selected_fields: Sequence of field names to fill.
        note_type_name: Name of the note type.
        batch_size: Number of notes per batch.
        addon_config: Addon configuration instance.
        user_files_dir: Directory for user files.
        on_success: Callback for transformation success.
            Called with (results, field_updates) when transformation completes successfully.
    """
    # Create NoteTransformer (UI-agnostic)
    transformer = NoteTransformer(
        col=col,
        selected_notes=selected_notes,
        note_ids=note_ids,
        lm_client=lm_client,
        prompt_builder=prompt_builder,
        selected_fields=selected_fields,
        note_type_name=note_type_name,
        batch_size=batch_size,
        addon_config=addon_config,
        user_files_dir=user_files_dir,
    )

    # Create progress dialog
    progress = QProgressDialog(
        f"Processing batch 0 of {transformer.num_batches}...",
        "Cancel",
        0,
        transformer.num_batches,
        parent,
    )
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)  # Show immediately
    progress.show()

    def process_batches(col: Collection) -> tuple[TransformResults, dict[NoteId, dict[str, str]]]:
        """Background operation that processes each batch."""
        # Create callbacks for progress and cancellation
        def progress_callback(current: int, total: int) -> None:
            def update_ui() -> None:
                progress.setLabelText(f"Processing batch {current + 1} of {total}...")
                progress.setValue(current)
            mw.taskman.run_on_main(update_ui)

        def should_cancel() -> bool:
            return progress.wasCanceled()

        # Run transformation with callbacks (always returns field updates)
        return transformer.get_field_updates(
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

    def on_success_callback(result_tuple: tuple[TransformResults, dict[NoteId, dict[str, str]]]) -> None:
        """Called when transformation succeeds."""
        progress.close()
        results, field_updates = result_tuple
        on_success(results, field_updates)

    def on_failure(exc: Exception) -> None:
        """Called when operation fails."""
        progress.close()
        showInfo(f"Error during transformation: {exc!s}", parent=parent)

    # Run the operation in the background
    QueryOp(
        parent=parent,
        op=lambda col: process_batches(col),
        success=on_success_callback,
    ).failure(on_failure).run_in_background()


def apply_field_updates_with_operation(
    parent: QWidget,
    col: Collection,
    field_updates: dict[NoteId, dict[str, str]],
    logger: logging.Logger,
    on_success: Callable[[dict[str, int]], None] | None = None,
    on_failure: Callable[[Exception], None] | None = None,
) -> None:
    """
    Apply stored field updates to the Anki collection using update_notes operation.

    Args:
        parent: Parent widget for the operation.
        col: Anki collection.
        field_updates: Dictionary mapping note_id -> dict of field_name -> new_value.
        logger: Logger instance.
        on_success: Callback called with results dict when operation succeeds.
        on_failure: Callback called with exception when operation fails.
    """
    # Collect notes that need updating
    notes_to_update = []
    failed = 0

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

    # Run CollectionOp to update notes
    def on_op_success(changes: Any) -> None:
        """Called when update notes operation succeeds."""
        if on_success:
            on_success({"updated": len(notes_to_update), "failed": failed})

    def on_op_failure(exception: Exception) -> None:
        """Called when update notes operation fails."""
        logger.error(f"Error in update notes operation: {exception!r}")
        if on_failure:
            on_failure(exception)

    # Run the operation
    CollectionOp(parent, lambda col: col.update_notes(notes_to_update)).success(on_op_success).failure(on_op_failure).run_in_background()
