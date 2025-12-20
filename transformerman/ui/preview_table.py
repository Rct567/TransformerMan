"""
Preview table widget for TransformerMan.

This module provides a dedicated QTableWidget subclass for displaying
note previews with background loading and highlighting capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from aqt.qt import (
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QColor,
    QWidget,
    QAbstractItemView,
    QMenu,
    QAction,
    QApplication,
    QContextMenuEvent,
)
from aqt.operations import QueryOp

from ..lib.utilities import batched, override
from ..lib.field_updates import FieldUpdates

import logging

if TYPE_CHECKING:
    from collections.abc import Sequence
    from anki.collection import Collection
    from anki.notes import NoteId, Note
    from ..lib.selected_notes import SelectedNotes


# Constants for content display
MAX_CONTENT_LENGTH = 50
ELLIPSIS_LENGTH = 3  # Length of "..."
TRUNCATED_LENGTH = MAX_CONTENT_LENGTH - ELLIPSIS_LENGTH
BATCH_SIZE = 10

# Color constants for highlighting
DARK_MODE_HIGHLIGHT_COLOR = (50, 150, 50)  # Dark green
LIGHT_MODE_HIGHLIGHT_COLOR = (200, 255, 200)  # Light green
DARK_MODE_DIM_HIGHLIGHT_COLOR = (65, 100, 65)  # Dimmer dark green
LIGHT_MODE_DIM_HIGHLIGHT_COLOR = (200, 240, 200)  # Dimmer light green
DARK_MODE_DIM_TEXT_COLOR = (150, 180, 150)  # Dimmed text for dark mode
LIGHT_MODE_DIM_TEXT_COLOR = (100, 140, 100)  # Dimmed text for light mode


class TableNoteData(TypedDict):
    """Data structure for note information used in background loading for the preview table."""
    note: Note
    note_updates: dict[str, str]  # Field updates from preview transformation (field_name -> new_value)


class PreviewTable(QTableWidget):
    """Table widget for displaying note previews with background loading."""

    selected_notes: SelectedNotes | None
    highlight_color: QColor
    dim_highlight_color: QColor
    dim_text_color: QColor
    is_highlighted: bool

    def __init__(
        self,
        parent: QWidget,
        is_dark_mode: bool,
    ) -> None:
        """
        Initialize the preview table.

        Args:
            parent: Parent widget.
            is_dark_mode: Whether the application is in dark mode.
        """
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.logger = logging.getLogger(__name__)

        # Configure table appearance
        self.setAlternatingRowColors(True)
        vertical_header = self.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(False)
        self.setMinimumHeight(150)

        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Set highlight colors based on dark mode (always available)
        if self.is_dark_mode:
            # Dark mode - use darker greens
            self.highlight_color = QColor(*DARK_MODE_HIGHLIGHT_COLOR)
            self.dim_highlight_color = QColor(*DARK_MODE_DIM_HIGHLIGHT_COLOR)
            self.dim_text_color = QColor(*DARK_MODE_DIM_TEXT_COLOR)
        else:
            # Light mode - use light greens
            self.highlight_color = QColor(*LIGHT_MODE_HIGHLIGHT_COLOR)
            self.dim_highlight_color = QColor(*LIGHT_MODE_DIM_HIGHLIGHT_COLOR)
            self.dim_text_color = QColor(*LIGHT_MODE_DIM_TEXT_COLOR)

        # State
        self.selected_notes = None
        self.is_highlighted = False

    def set_selected_notes(self, selected_notes: SelectedNotes) -> None:
        """Set the selected notes instance for loading notes."""
        self.selected_notes = selected_notes

    def show_notes(
        self,
        note_ids: Sequence[NoteId],
        selected_fields: list[str],
        field_updates: FieldUpdates | None = None,
    ) -> None:
        """
        Display notes in the table with selected fields and optional highlighting.

        Args:
            note_ids: List of note IDs to display.
            selected_fields: List of selected field names (column headers).
            field_updates: Optional FieldUpdates instance for highlighting.
        """
        if not note_ids or not selected_fields:
            self.clear()
            self.setColumnCount(0)
            self.setRowCount(0)
            return

        # Setup columns
        self.setColumnCount(len(selected_fields))
        self.setHorizontalHeaderLabels(selected_fields)

        # Set row count
        self.setRowCount(len(note_ids))

        # Load notes in background
        self._load_notes_in_background(list(note_ids), selected_fields, field_updates)

    def _create_table_item(
        self, full_content: str, is_highlighted: bool, is_dim_highlight: bool = False
    ) -> QTableWidgetItem:
        """
        Create a table widget item with truncated content and appropriate styling.

        Args:
            full_content: The complete content string.
            is_highlighted: Whether to apply highlight styling.
            is_dim_highlight: Whether to use dim highlight (when update matches original).

        Returns:
            A QTableWidgetItem with truncated content, tooltip, and optional highlighting.
        """
        # Truncate content if needed
        if len(full_content) > MAX_CONTENT_LENGTH:
            display_content = full_content[:TRUNCATED_LENGTH] + "..."
        else:
            display_content = full_content

        item = QTableWidgetItem(display_content)
        item.setToolTip(full_content)

        if is_highlighted and self.is_highlighted:
            if is_dim_highlight:
                item.setBackground(self.dim_highlight_color)
                item.setForeground(self.dim_text_color)
            else:
                item.setBackground(self.highlight_color)

        return item

    def _load_notes_in_background(
        self,
        note_ids: list[NoteId],
        selected_fields: list[str],
        field_updates: FieldUpdates | None = None,
    ) -> None:
        """
        Load notes in batches in a background thread and update the table as they come in.

        Args:
            note_ids: List of note IDs to load.
            selected_fields: List of selected field names.
            field_updates: Optional FieldUpdates instance for preview highlighting.
        """
        selected_notes = self.selected_notes
        if selected_notes is None:
            return

        # Set whether the table should be in highlighted mode
        self.is_highlighted = field_updates is not None

        # Store the current state for the background operation
        current_ids = note_ids.copy()
        current_selected_fields = selected_fields.copy()
        current_field_updates = field_updates if field_updates else FieldUpdates()

        def load_notes_batch(_: Collection) -> list[tuple[int, TableNoteData]]:
            """Background operation that loads notes in batches."""
            loaded_data: list[tuple[int, TableNoteData]] = []
            row_index = 0

            # Use batched utility function for cleaner batch processing
            for batch_ids in batched(current_ids, BATCH_SIZE):

                # Load notes for this batch
                notes = selected_notes.get_notes(batch_ids)

                # Process each note in the batch
                for i, note in enumerate(notes):
                    note_data: TableNoteData = {
                        "note": note,
                        "note_updates": current_field_updates.get(note.id, {}),
                    }
                    loaded_data.append((row_index + i, note_data))

                row_index += len(notes)

            return loaded_data

        def on_batch_loaded(result: list[tuple[int, TableNoteData]]) -> None:
            """Update the table with loaded notes."""
            for row_index, data in result:
                note = data["note"]
                note_updates = data["note_updates"]

                for col, field_name in enumerate(current_selected_fields):
                    # Check if field exists in note
                    try:
                        # Check if this field has a preview update
                        if field_name in note_updates:
                            # Show preview value with green background
                            full_content = note_updates[field_name]
                            is_highlighted = True
                            is_dim_highlight = full_content == note[field_name]
                        else:
                            # Show original value
                            full_content = note[field_name]
                            is_highlighted = False
                            is_dim_highlight = False

                        # Create table item with truncated content if needed
                        item = self._create_table_item(
                            full_content=full_content,
                            is_highlighted=is_highlighted,
                            is_dim_highlight=is_dim_highlight,
                        )
                        self.setItem(row_index, col, item)
                    except (KeyError, AttributeError):
                        # Field doesn't exist in note or note is invalid
                        item = QTableWidgetItem("")
                        self.setItem(row_index, col, item)

            # Adjust column widths
            header = self.horizontalHeader()
            if header:
                header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        def on_failure(exc: Exception) -> None:
            """Handle failure in background loading."""
            self.logger.error(f"Error loading notes in background: {exc!s}")

        # Run the operation in the background
        QueryOp(
            parent=self,
            op=lambda col: load_notes_batch(col),
            success=on_batch_loaded,
        ).failure(on_failure).run_in_background()

    @override
    def contextMenuEvent(self, a0: QContextMenuEvent | None) -> None:
        """Handle right-click context menu event."""
        if a0 is None:
            return

        selected_items = self.selectedItems()
        if not selected_items:
            return

        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(lambda: self._copy_selected_cells())
        menu.addAction(copy_action)

        menu.exec(a0.globalPos())

    def _copy_selected_cells(self) -> None:
        """Copy the text content of selected cells to clipboard."""
        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Organize selected items by row and column to preserve table structure
        selected_cells: dict[tuple[int, int], str] = {}
        for item in selected_items:
            row = item.row()
            col = item.column()
            # Try to get full content from tooltip first
            tooltip = item.toolTip()
            if tooltip:
                selected_cells[row, col] = tooltip
            else:
                # Fall back to display text if no tooltip
                display_text = item.text()
                if display_text:
                    selected_cells[row, col] = display_text

        if not selected_cells:
            return

        # Get the range of rows and columns
        rows = sorted(set(row for row, _ in selected_cells))
        cols = sorted(set(col for _, col in selected_cells))

        # Build clipboard text preserving table structure
        # Use tab-separated columns and newline-separated rows
        clipboard_lines: list[str] = []
        for row in rows:
            row_texts: list[str] = []
            for col in cols:
                cell_text = selected_cells.get((row, col), "")
                row_texts.append(cell_text)
            clipboard_lines.append("\t".join(row_texts))

        clipboard_text = "\n".join(clipboard_lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(clipboard_text)
