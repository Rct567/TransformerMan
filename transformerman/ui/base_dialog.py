"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import QDialog, QWidget
from aqt.utils import saveGeom, restoreGeom

from ..lib.utilities import override
from .utilities import get_tm_icon

if TYPE_CHECKING:
    from aqt.qt import QCloseEvent


class TransformerManBaseDialog(QDialog):
    """Base dialog for TransformerMan with geometry saving/restoring."""

    def __init__(self, parent: QWidget | None, is_dark_mode: bool) -> None:
        """
        Initialize the base dialog.

        Args:
            parent: Parent widget (typically the main Anki window).
        """
        super().__init__(parent)
        # Set the TransformerMan icon
        self.setWindowIcon(get_tm_icon(is_dark_mode))
        # Generate a unique geometry key based on the class name
        geometry_key = f"transformerman_{self.__class__.__name__}"
        restoreGeom(self, geometry_key)

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """
        Handle window close event.

        Saves the dialog geometry before closing.

        Args:
            a0: Close event.
        """
        if a0 is not None:
            geometry_key = f"transformerman_{self.__class__.__name__}"
            saveGeom(self, geometry_key)
        super().closeEvent(a0)
