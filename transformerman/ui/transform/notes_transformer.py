"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from aqt import mw
from aqt.operations import QueryOp, CollectionOp
from aqt.utils import showInfo

from ...lib.transform_operations import CacheKey, NoteTransformer, TransformResults
from ...lib.transform_prompt_builder import TransformPromptBuilder

from ..progress_dialog import ProgressDialog

if TYPE_CHECKING:
    from aqt.qt import QWidget
    from anki.collection import Collection, OpChanges
    from ...lib.field_updates import FieldUpdates
    from .field_widgets import FieldSelection
    from ...lib.http_utils import LmProgressData
    from ...lib.response_middleware import ResponseMiddleware
    from ...lib.addon_config import AddonConfig
    from ...lib.lm_clients import LMClient
    from ...lib.selected_notes import SelectedNotes, SelectedNotesFromType


class NotesTransformer:
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
        middleware: ResponseMiddleware,
    ) -> None:
        """
        Initialize the transformer.

        Args:
            parent: Parent widget for dialogs.
            col: Anki collection.
            selected_notes: SelectedNotes instance.
            lm_client: LM client instance.
            addon_config: Addon configuration instance.
            middleware: Response middleware instance.
        """
        self.parent = parent
        self.col = col
        self.selected_notes = selected_notes
        self.lm_client = lm_client
        self.addon_config = addon_config
        self.middleware = middleware
        self.logger = logging.getLogger(__name__)
        self._prompt_builder = TransformPromptBuilder(col)

        # Cache for transformation results
        self._cache = {}

    def _get_cache_key(
        self,
        selected_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
    ) -> CacheKey:
        """Generate a cache key for the given transformation parameters."""
        # Create a hash of field_instructions for cache key
        # Sort items to ensure consistent hash for same instructions
        field_instructions_items = sorted(self._prompt_builder.field_instructions.items())
        field_instructions_hash = hash(tuple(field_instructions_items))

        return CacheKey(
            client_id=self.lm_client.id,
            note_type_name=selected_notes.note_type.name,
            selected_fields=tuple(field_selection.selected),
            writable_fields=tuple(field_selection.writable),
            overwritable_fields=tuple(field_selection.overwritable),
            note_ids=tuple(selected_notes.get_ids()),
            max_prompt_size=self.addon_config.get_max_prompt_size(),
            max_notes_per_batch=self.addon_config.get_max_notes_per_batch(),
            field_instructions_hash=field_instructions_hash,
        )

    def is_cached(
        self,
        selected_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
    ) -> bool:
        """
        Check if transformation results are cached.

        Args:
            selected_notes: SelectedNotesFromType instance containing notes and note type.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.

        Returns:
            True if results are cached, False otherwise.
        """
        cache_key = self._get_cache_key(selected_notes, field_selection)
        return cache_key in self._cache

    def get_num_api_calls_needed(
        self,
        selected_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
    ) -> int:
        """
        Calculate the number of API calls needed for the given parameters.
        If results are already cached, returns 0. Otherwise, calculates based on
        actual prompt batching.

        Args:
            selected_notes: SelectedNotesFromType instance containing notes and note type.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.

        Returns:
            Number of API calls needed.
        """
        # If cached, no API calls needed
        if self.is_cached(selected_notes, field_selection):
            return 0

        if not field_selection.writable and not field_selection.overwritable:
            return 0

        # Get notes with empty fields in writable_fields OR notes with fields in overwritable_fields
        notes_with_fields = selected_notes.filter_by_writable_or_overwritable(field_selection.writable, field_selection.overwritable)

        if not notes_with_fields:
            return 0

        # Calculate actual batches
        batches = notes_with_fields.batched_by_prompt_size(
            prompt_builder=self._prompt_builder,
            field_selection=field_selection,
            max_chars=self.addon_config.get_max_prompt_size(),
            max_notes_per_batch=self.addon_config.get_max_notes_per_batch(),
            max_examples=self.addon_config.get_max_examples(),
        )

        return len(batches)

    def transform(
        self,
        selected_notes: SelectedNotesFromType,
        field_selection: FieldSelection,
        on_success: Callable[[TransformResults, FieldUpdates], None],
        prompt_interceptor: Callable[[str], str] | None = None,
    ) -> None:
        """
        Transform notes in batches with progress tracking.

        Makes API calls to get field updates and returns them via the on_success callback.
        Results are cached for future calls with the same parameters.

        Args:
            selected_notes: SelectedNotesFromType instance containing notes and note type.
            field_selection: FieldSelection containing selected, writable, and overwritable fields.
            on_success: Callback for transformation success.
                Called with (results, field_updates) when transformation completes successfully.
            prompt_interceptor: Optional function to intercept and modify the prompt template before use.
        """
        # Check cache first
        cache_key = self._get_cache_key(selected_notes, field_selection)
        if cache_key in self._cache:
            results, field_updates = self._cache[cache_key]
            on_success(results, field_updates)
            return

        # Create NoteTransformer (UI-agnostic)
        transformer = NoteTransformer(
            col=self.col,
            selected_notes=selected_notes,
            lm_client=self.lm_client,
            prompt_builder=self._prompt_builder,
            field_selection=field_selection,
            addon_config=self.addon_config,
            middleware=self.middleware,
            prompt_interceptor=prompt_interceptor,
        )

        # Create custom progress dialog
        progress = ProgressDialog(transformer.num_batches, self.parent)
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
        num_notes_txt = "1 note" if len(notes_to_update) == 1 else f"{len(notes_to_update)} notes"
        pos = col.add_custom_undo_entry("Transforming fields ({})".format(num_notes_txt))
        col.update_notes(notes_to_update)
        return col.merge_undo_entries(pos)

    # Run the operation
    CollectionOp(parent, op=transform_operation).success(on_op_success).failure(on_op_failure).run_in_background()
