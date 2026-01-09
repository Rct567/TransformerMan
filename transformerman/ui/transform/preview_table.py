"""
Preview table widget for TransformerMan.

This module provides a dedicated QTableWidget subclass for displaying
note previews with background loading and highlighting capabilities.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from typing import TYPE_CHECKING, TypedDict
import difflib

from aqt.qt import (
    QTableWidget,
    QTableWidgetItem,
    QColor,
    QWidget,
    QAbstractItemView,
    QMenu,
    QAction,
    QApplication,
    QContextMenuEvent,
)
from aqt.operations import QueryOp

from ...lib.utilities import batched, override
from ...lib.field_updates import FieldUpdates

import logging

if TYPE_CHECKING:
    from collections.abc import Sequence, Callable
    from anki.collection import Collection
    from anki.notes import NoteId, Note
    from ...lib.selected_notes import SelectedNotes


# Constants for content display
MAX_CONTENT_LENGTH = 1000
ELLIPSIS_LENGTH = 3  # Length of "..."
TRUNCATED_LENGTH = MAX_CONTENT_LENGTH - ELLIPSIS_LENGTH

# Color constants for highlighting
DARK_MODE_HIGHLIGHT_COLOR = (50, 150, 50)  # Dark green
LIGHT_MODE_HIGHLIGHT_COLOR = (200, 255, 200)  # Light green
DARK_MODE_DIM_HIGHLIGHT_COLOR = (65, 100, 65)  # Dimmer dark green
LIGHT_MODE_DIM_HIGHLIGHT_COLOR = (200, 240, 200)  # Dimmer light green
DARK_MODE_DIM_TEXT_COLOR = (150, 180, 150)  # Dimmed text for dark mode
LIGHT_MODE_DIM_TEXT_COLOR = (100, 140, 100)  # Dimmed text for light mode

# Diff tooltip constants
DIFF_CONTEXT_LENGTH = 40  # Characters of context to show around changes
MAX_SIMPLE_DIFF_LENGTH = 200  # If both strings are shorter, show full diff


def _create_diff_tooltip(old_content: str, new_content: str) -> str:
    """
    Create a smart tooltip showing the difference between old and new content.

    For short content, shows both old and new values in full.
    For long content, shows only the changed sections with context.

    Args:
        old_content: The original content.
        new_content: The updated content.

    Returns:
        A formatted tooltip string showing the differences.
    """
    # If content is identical, just show it once
    if old_content == new_content:
        return new_content

    # For short content, show both old and new in full
    if len(old_content) <= MAX_SIMPLE_DIFF_LENGTH and len(new_content) <= MAX_SIMPLE_DIFF_LENGTH:
        return f"Old: {old_content}\n\nNew: {new_content}"

    # For long content, use smart diffing to show only changes
    # Split into lines for better diff granularity
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Use SequenceMatcher to find differences
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    diff_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Skip equal parts, but show context if they're short
            equal_content = "".join(old_lines[i1:i2])
            if len(equal_content) <= DIFF_CONTEXT_LENGTH * 2:
                diff_parts.append(equal_content)
            else:
                # Show beginning and end context
                context_start = "".join(old_lines[i1 : i1 + 1])[:DIFF_CONTEXT_LENGTH]
                context_end = "".join(old_lines[i2 - 1 : i2])[-DIFF_CONTEXT_LENGTH:]
                if context_start:
                    diff_parts.append(context_start)
                diff_parts.append("\n[...]\n")
                if context_end:
                    diff_parts.append(context_end)
        elif tag == "replace":
            old_text = "".join(old_lines[i1:i2])
            new_text = "".join(new_lines[j1:j2])
            diff_parts.append(f"\n[-] {old_text}")
            diff_parts.append(f"\n[+] {new_text}\n")
        elif tag == "delete":
            old_text = "".join(old_lines[i1:i2])
            diff_parts.append(f"\n[-] {old_text}\n")
        elif tag == "insert":
            new_text = "".join(new_lines[j1:j2])
            diff_parts.append(f"\n[+] {new_text}\n")

    if not diff_parts:
        # Fallback to simple diff if no changes detected
        return f"Old: {old_content}\n\nNew: {new_content}"

    return "".join(diff_parts).strip()


class TableNoteData(TypedDict):
    """Data structure for note information used in background loading for the preview table."""
    note: Note
    note_updates: dict[str, str]  # Field updates from preview transformation (field_name -> new_value)


class PreviewTable(QTableWidget):
    """Table widget for displaying note previews with background loading."""

    highlight_color: QColor
    dim_highlight_color: QColor
    dim_text_color: QColor
    is_highlighted: bool
    get_notes: Callable[[Sequence[NoteId]], Sequence[Note]]
    current_note_ids: list[NoteId] | None
    current_selected_fields: Sequence[str] | None
    current_field_updates: FieldUpdates | None

    def __init__(
        self,
        parent: QWidget,
        is_dark_mode: bool,
        get_notes: Callable[[Sequence[NoteId]], Sequence[Note]]
    ) -> None:
        """
        Initialize the preview table.

        Args:
            parent: Parent widget.
            is_dark_mode: Whether the application is in dark mode.
            get_notes: Function to get notes by ID.
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
        self.get_notes = get_notes
        self.is_highlighted = False
        self.current_note_ids = None  # currently displayed notes
        self.current_selected_fields = None  # currently displayed fields
        self.current_field_updates = None  # highlighted mode

    def _set_column_widths(self) -> None:

        horizontal_header = self.horizontalHeader()
        assert horizontal_header

        column_count = self.columnCount()
        for col_index in range(column_count):
            horizontal_header.setSectionResizeMode(col_index, horizontal_header.ResizeMode.Interactive)

        # Set default column widths
        if table_viewport := self.viewport():
            table_width = table_viewport.width()
            default_column_width = min(table_width // column_count, 400)
            for col_index in range(column_count):
                self.setColumnWidth(col_index, default_column_width)

    def show_notes(
        self,
        selected_notes: SelectedNotes,
        selected_fields: Sequence[str],
        field_updates: FieldUpdates | None = None,
    ) -> None:
        """
        Display notes in the table with selected fields and optional highlighting.

        Args:
            selected_notes: SelectedNotes instance containing notes to display.
            selected_fields: Sequence of note fields to show (column headers).
            field_updates: Optional FieldUpdates instance for highlighting.
        """
        if not selected_notes or not selected_fields:
            self.clear()
            self.setColumnCount(0)
            self.setRowCount(0)
            return

        # Store current display parameters
        self.current_note_ids = list(selected_notes.get_ids())
        self.current_selected_fields = list(selected_fields)
        self.current_field_updates = field_updates

        # Temporarily disable updates
        self.setDisabled(True)
        self.setUpdatesEnabled(False)

        # Setup columns
        self.setColumnCount(len(selected_fields))
        self.setHorizontalHeaderLabels(selected_fields)

        # Set row count
        self.setRowCount(len(selected_notes))

        # Make the last column stretch to fill remaining space
        horizontal_header = self.horizontalHeader()
        assert horizontal_header
        horizontal_header.setStretchLastSection(True)

        # Load notes in background
        self._load_notes_in_background()

        # Set column widths
        QTimer.singleShot(0, self._set_column_widths)

        # Enable updates again
        self.setDisabled(False)
        self.setUpdatesEnabled(True)

    def _create_table_item(
        self, full_content: str, is_highlighted: bool, is_dim_highlight: bool = False, old_content: str | None = None
    ) -> QTableWidgetItem:
        """
        Create a table widget item with truncated content and appropriate styling.

        Args:
            full_content: The complete content string (new content).
            is_highlighted: Whether to apply highlight styling.
            is_dim_highlight: Whether to use dim highlight (when update matches original).
            old_content: Optional original content for creating diff tooltips.

        Returns:
            A QTableWidgetItem with truncated content, tooltip, and optional highlighting.
        """
        # Truncate content if needed
        if len(full_content) > MAX_CONTENT_LENGTH:
            display_content = full_content[:TRUNCATED_LENGTH] + "..."
        else:
            display_content = full_content

        item = QTableWidgetItem(display_content)

        # Create smart diff tooltip if we have old content and it's different
        if old_content is not None and old_content != full_content:
            tooltip = _create_diff_tooltip(old_content, full_content)
            item.setToolTip(tooltip)
        else:
            # Use full content as tooltip
            item.setToolTip(full_content)

        if is_highlighted and self.is_highlighted:
            if is_dim_highlight:
                item.setBackground(self.dim_highlight_color)
                item.setForeground(self.dim_text_color)
            else:
                item.setBackground(self.highlight_color)

        return item

    def _load_notes_in_background(self) -> None:
        """
        Load notes in batches in a background thread and update the table as they come in.
        """
        if not self.current_note_ids or self.current_selected_fields is None:
            return

        # At this point, current_note_ids and current_selected_fields are guaranteed to be not None
        current_note_ids = self.current_note_ids
        current_selected_fields = self.current_selected_fields

        # Set whether the table should be in highlighted mode
        self.is_highlighted = self.current_field_updates is not None

        current_field_updates = self.current_field_updates if self.current_field_updates else FieldUpdates()

        def load_notes(_: Collection) -> list[TableNoteData]:
            """Background operation that loads notes in batches."""
            loaded_data: list[TableNoteData] = []

            for batch_ids in batched(current_note_ids, 1000):
                for note in self.get_notes(batch_ids):
                    note_data: TableNoteData = {
                        "note": note,
                        "note_updates": current_field_updates.get(note.id, {}),
                    }
                    loaded_data.append(note_data)

            return loaded_data

        def on_notes_loaded(result: list[TableNoteData]) -> None:
            """Update the table with loaded notes."""
            for row_index, data in enumerate(result):
                note = data["note"]
                note_updates = data["note_updates"]

                for col, field_name in enumerate(current_selected_fields):
                    # Check if field exists in note
                    try:
                        # Check if this field has a preview update
                        if field_name in note_updates:
                            # Show preview value with green background
                            full_content = note_updates[field_name]
                            old_content = note[field_name]
                            is_highlighted = True
                            is_dim_highlight = full_content == old_content
                        else:
                            # Show original value
                            full_content = note[field_name]
                            old_content = None
                            is_highlighted = False
                            is_dim_highlight = False

                        # Create table item with truncated content if needed
                        item = self._create_table_item(
                            full_content=full_content,
                            is_highlighted=is_highlighted,
                            is_dim_highlight=is_dim_highlight,
                            old_content=old_content,
                        )
                        self.setItem(row_index, col, item)
                    except (KeyError, AttributeError):
                        # Field doesn't exist in note or note is invalid
                        item = QTableWidgetItem("")
                        self.setItem(row_index, col, item)

        def on_failure(exc: Exception) -> None:
            """Handle failure in background loading."""
            self.logger.error(f"Error loading notes in background: {exc!s}")

        # Run the operation in the background
        QueryOp(
            parent=self,
            op=lambda col: load_notes(col),
            success=on_notes_loaded,
        ).failure(on_failure).run_in_background()

    @override
    def contextMenuEvent(self, a0: QContextMenuEvent | None) -> None:
        """Handle right-click context menu event."""
        if a0 is None:
            return

        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Check if any selected rows have highlighted cells (field updates)
        has_highlighted_rows = False
        if self.current_field_updates is not None and self.current_note_ids is not None:
            selected_rows = set(item.row() for item in selected_items)
            for row in selected_rows:
                if row < len(self.current_note_ids):
                    note_id = self.current_note_ids[row]
                    if note_id in self.current_field_updates:
                        has_highlighted_rows = True
                        break

        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(lambda: self._copy_selected_cells())
        menu.addAction(copy_action)

        if has_highlighted_rows:
            menu.addSeparator()
            discard_action = QAction("Discard", self)
            discard_action.triggered.connect(lambda: self._discard_selected_rows())
            menu.addAction(discard_action)

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

    def refresh(self) -> None:
        """Refresh the table display with current data."""
        if self.current_note_ids is None or self.current_selected_fields is None:
            return

        # Temporarily disable updates
        self.setDisabled(True)
        self.setUpdatesEnabled(False)

        # Reload notes in background
        self._load_notes_in_background()

        # Enable updates again
        self.setDisabled(False)
        self.setUpdatesEnabled(True)

    def _discard_selected_rows(self) -> None:
        """Discard field updates for selected rows that have updates."""
        if self.current_field_updates is None or self.current_note_ids is None or self.current_selected_fields is None:
            return

        selected_items = self.selectedItems()
        if not selected_items:
            return

        selected_rows = set(item.row() for item in selected_items)

        # Remove updates for selected rows that have them
        for row in selected_rows:
            if row < len(self.current_note_ids):
                note_id = self.current_note_ids[row]
                self.current_field_updates.remove_note_updates(note_id)

        # Refresh the table with updated field_updates
        self.refresh()
