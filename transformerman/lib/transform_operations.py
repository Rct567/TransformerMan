"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from aqt import mw
from aqt.operations import QueryOp
from aqt.utils import showInfo, tooltip
from aqt.qt import QProgressDialog, QWidget, Qt

if TYPE_CHECKING:
    from pathlib import Path
    from anki.collection import Collection
    from anki.notes import NoteId
    from .addon_config import AddonConfig
    from .lm_clients import LMClient, LmResponse
    from .prompt_builder import PromptBuilder
    from .selected_notes import SelectedNotes


def create_lm_logger(addon_config: AddonConfig, user_files_dir: Path) -> tuple[Callable[[str], None], Callable[[LmResponse], None]]:
    """Create logging functions for LM requests and responses."""
    logs_dir = user_files_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)

    def log_request(prompt: str) -> None:
        if addon_config.is_enabled("log_lm_requests", False):
            requests_file = logs_dir / 'lm_requests.log'
            timestamp = datetime.now().isoformat()
            with requests_file.open('a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {prompt}\n\n")

    def log_response(response: LmResponse) -> None:
        if addon_config.is_enabled("log_lm_responses", False):
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
        note_ids: list[NoteId],
        lm_client: LMClient,
        prompt_builder: PromptBuilder,
        selected_fields: set[str],
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
            selected_fields: Set of field names to fill.
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

        # Validate that we have notes with empty fields
        notes_to_transform = self.selected_notes.get_selected_notes(self.note_ids)
        if not notes_to_transform.has_note_with_empty_field(self.selected_fields):
            raise ValueError("No notes with empty fields found")

        # Create batches
        self.batches = notes_to_transform.create_batches(self.batch_size)
        self.total_batches = len(self.batches)

    def _handle_batch(
        self,
        batch_selected_notes: SelectedNotes,
        log_request: Callable[[str], None],
        log_response: Callable[[LmResponse], None],
    ) -> tuple[int, int]:
        """
        Process a single batch of notes.

        Args:
            batch_selected_notes: Batch of notes to process.
            log_request: Function to log LM requests.
            log_response: Function to log LM responses.

        Returns:
            Tuple of (updated_count, failed_count) for this batch.
        """
        updated = 0
        failed = 0

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

            # Parse response
            field_updates = response.get_notes_from_xml()

            # Update notes
            for nid in batch_selected_notes.note_ids:
                try:
                    note = self.col.get_note(nid)
                    updates = field_updates.get(nid, {})

                    note_updated = False
                    for field_name, content in updates.items():
                        # Only update if field is in selected fields and is empty
                        if field_name in self.selected_fields and not note[field_name].strip():
                            note[field_name] = content
                            note_updated = True

                    if note_updated:
                        self.col.update_note(note)
                        updated += 1

                except Exception as e:
                    print(f"Error updating note {nid}: {e!r}")
                    failed += 1
                    continue

        except Exception as e:
            print(f"Error processing batch: {e!r}")
            failed += len(batch_selected_notes.note_ids)

        return updated, failed

    def transform(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        """
        Transform notes in batches.

        Args:
            progress_callback: Optional callback for progress reporting.
                Called with (current_batch, total_batches).
            should_cancel: Optional callback to check if operation should be canceled.
                Should return True if operation should be canceled.

        Returns:
            Dictionary with transformation results:
                - "updated": Number of fields updated
                - "failed": Number of notes that failed
                - "batches_processed": Number of batches processed
        """
        total_updated = 0
        total_failed = 0
        batch_idx = 0

        log_request, log_response = create_lm_logger(self.addon_config, self.user_files_dir)

        for batch_idx, batch_selected_notes in enumerate(self.batches):
            # Check if operation should be canceled
            if should_cancel and should_cancel():
                break

            # Report progress
            if progress_callback:
                progress_callback(batch_idx, self.total_batches)

            # Process batch
            updated, failed = self._handle_batch(batch_selected_notes, log_request, log_response)
            total_updated += updated
            total_failed += failed

        # Report completion
        if progress_callback:
            progress_callback(self.total_batches, self.total_batches)

        return {
            "updated": total_updated,
            "failed": total_failed,
            "batches_processed": batch_idx + 1 if not (should_cancel and should_cancel()) else batch_idx,
        }


def transform_notes_with_progress(  # noqa: PLR0913
    parent: QWidget,
    col: Collection,
    selected_notes: SelectedNotes,
    note_ids: list[NoteId],
    lm_client: LMClient,
    prompt_builder: PromptBuilder,
    selected_fields: set[str],
    note_type_name: str,
    batch_size: int,
    addon_config: AddonConfig,
    user_files_dir: Path,
) -> None:
    """
    Transform notes in batches with progress tracking.

    Args:
        parent: Parent widget for dialogs.
        col: Anki collection.
        selected_notes: SelectedNotes instance.
        note_ids: List of note IDs to transform.
        lm_client: LM client instance.
        prompt_builder: Prompt builder instance.
        selected_fields: Set of field names to fill.
        note_type_name: Name of the note type.
        batch_size: Number of notes per batch.
        addon_config: Addon configuration instance.
        user_files_dir: Directory for user files.
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
        f"Processing batch 0 of {transformer.total_batches}...",
        "Cancel",
        0,
        transformer.total_batches,
        parent,
    )
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)  # Show immediately
    progress.show()

    def process_batches(col: Collection) -> dict[str, int]:
        """Background operation that processes each batch."""
        # Create callbacks for progress and cancellation
        def progress_callback(current: int, total: int) -> None:
            def update_ui() -> None:
                progress.setLabelText(f"Processing batch {current + 1} of {total}...")
                progress.setValue(current)
            mw.taskman.run_on_main(update_ui)

        def should_cancel() -> bool:
            return progress.wasCanceled()

        # Run transformation with callbacks
        return transformer.transform(
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

    def on_success(results: dict[str, int]) -> None:
        """Called when operation succeeds."""
        progress.close()
        message = "Transformation complete!\n\n"
        message += f"Batches processed: {results['batches_processed']}/{transformer.total_batches}\n"
        message += f"Fields updated: {results['updated']}\n"
        if results['failed'] > 0:
            message += f"Failed notes: {results['failed']}"
        tooltip(message)

    def on_failure(exc: Exception) -> None:
        """Called when operation fails."""
        progress.close()
        showInfo(f"Error during transformation: {exc!s}")

    # Run the operation in the background
    QueryOp(
        parent=parent,
        op=lambda col: process_batches(col),
        success=on_success,
    ).failure(on_failure).run_in_background()
