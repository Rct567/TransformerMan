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
                f.write(f"[{timestamp}] {response.raw_response}\n\n")

    return log_request, log_response


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
    """


    # Create batches
    batches = selected_notes.create_batches(note_ids, batch_size)
    total_batches = len(batches)

    # Create progress dialog
    progress = QProgressDialog(
        f"Processing batch 0 of {total_batches}...",
        "Cancel",
        0,
        total_batches,
        parent,
    )
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)  # Show immediately
    progress.show()

    def process_batches(col: Collection) -> dict[str, int]:
        """Background operation that processes each batch."""
        total_updated = 0
        total_failed = 0
        batch_idx = 0

        log_request, log_response = create_lm_logger(addon_config, user_files_dir)

        for batch_idx, batch_note_ids in enumerate(batches):
                if progress.wasCanceled():
                    break

                # Update progress dialog
                def update_progress_ui(b: int) -> None:
                    progress.setLabelText(f"Processing batch {b + 1} of {total_batches}...")
                    progress.setValue(b)

                mw.taskman.run_on_main(lambda b=batch_idx: update_progress_ui(b)) # type: ignore[misc]

                try:
                    # Get notes for this batch
                    notes = selected_notes.get_notes(batch_note_ids)

                    # Build prompt
                    prompt = prompt_builder.build_prompt(col, notes, selected_fields, note_type_name)

                    # Log request
                    log_request(prompt)

                    # Get LM response
                    response = lm_client.transform(prompt)

                    # Log response
                    log_response(response)

                    # Parse response
                    field_updates = response.get_notes_from_xml()

                    # Update notes
                    for nid in batch_note_ids:
                        try:
                            note = col.get_note(nid)
                            updates = field_updates.get(nid, {})

                            for field_name, content in updates.items():
                                # Only update if field is in selected fields and is empty
                                if field_name in selected_fields and not note[field_name].strip():
                                    note[field_name] = content
                                    total_updated += 1

                            col.update_note(note)

                        except Exception as e:
                            print(f"Error updating note {nid}: {e!r}")
                            total_failed += 1
                            continue

                except Exception as e:
                    print(f"Error processing batch {batch_idx}: {e!r}")
                    total_failed += len(batch_note_ids)
                    continue

        mw.taskman.run_on_main(lambda: progress.setValue(total_batches))

        return {
            "updated": total_updated,
            "failed": total_failed,
            "batches_processed": batch_idx + 1 if not progress.wasCanceled() else batch_idx,
        }

    def on_success(results: dict[str, int]) -> None:
        """Called when operation succeeds."""
        progress.close()
        message = "Transformation complete!\n\n"
        message += f"Batches processed: {results['batches_processed']}/{total_batches}\n"
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
