"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from aqt.qt import QSpinBox, QValidator
from typing import TYPE_CHECKING

from ..lib.utilities import override

if TYPE_CHECKING:
    from aqt.qt import QWidget


class FormattedSpinBox(QSpinBox):
    """
    A QSpinBox that displays large numbers with underscore separators for better readability.

    Example: 500000 -> "500_000"
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

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

        # Remove underscores and any other non-digit characters (except minus sign)
        cleaned = text.replace("_", "").replace(" ", "")
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

        # Allow digits, underscores, and spaces
        cleaned = input.replace("_", "").replace(" ", "")

        if cleaned == "":
            return QValidator.State.Intermediate, input, pos

        try:
            int(cleaned)
            return QValidator.State.Acceptable, input, pos
        except ValueError:
            return QValidator.State.Invalid, input, pos
