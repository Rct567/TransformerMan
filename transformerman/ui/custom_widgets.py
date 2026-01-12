"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from aqt.qt import QSpinBox, QValidator, QTableWidget, QWidget

from ..lib.utilities import override


class TableWidget(QTableWidget):
    """A custom QTableWidget with additional functionality."""

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


class FormattedSpinBox(QSpinBox):
    """
    A QSpinBox that displays large numbers with underscore separators for better readability.

    Example: 500000 -> "500_000"
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def _strip_suffix_and_clean(self, text: str) -> str:
        """Remove suffix and clean text for parsing."""
        suffix = self.suffix()
        if suffix and text.endswith(suffix):
            text = text[:-len(suffix)]
        return text.replace("_", "").replace(" ", "").strip()

    @override
    def textFromValue(self, v: int) -> str:
        """
        Convert integer value to formatted string with underscore separators.

        Args:
            v: The integer value to format.

        Returns:
            Formatted string with underscore separators.
        """
        # Format with underscore separators
        # Convert to string and add underscores every 3 digits from the right
        s = str(v)
        parts = []
        # Process from right to left
        for i in range(len(s), 0, -3):
            start = max(0, i - 3)
            parts.append(s[start:i])
        # Reverse and join with underscores
        formatted = "_".join(reversed(parts))
        return formatted

    @override
    def valueFromText(self, text: str | None) -> int:
        """
        Convert formatted string back to integer value.

        Args:
            text: The formatted string (with or without underscores).

        Returns:
            Integer value.
        """
        if text is None:
            return 0

        cleaned = self._strip_suffix_and_clean(text)
        try:
            return int(cleaned)
        except ValueError:
            return 0

    @override
    def validate(self, input: str | None, pos: int) -> tuple[QValidator.State, str, int]:
        """
        Validate the input text.

        Args:
            input: The text to validate.
            pos: The cursor position.

        Returns:
            Tuple of (state, text, pos).
        """
        if input is None:
            return QValidator.State.Intermediate, "", pos

        cleaned = self._strip_suffix_and_clean(input)

        if cleaned == "":
            return QValidator.State.Intermediate, input, pos

        try:
            value = int(cleaned)
            if self.minimum() <= value <= self.maximum():
                return QValidator.State.Acceptable, input, pos
            else:
                return QValidator.State.Intermediate, input, pos
        except ValueError:
            return QValidator.State.Invalid, input, pos
