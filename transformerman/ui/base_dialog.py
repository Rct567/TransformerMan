"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import QDialog, QWidget
from aqt.utils import saveGeom, restoreGeom

from ..lib.utilities import override
from .ui_utilities import get_tm_icon

if TYPE_CHECKING:
    from aqt.qt import QCloseEvent


tm_version: str

try:
    from ..version import TRANSFORMERMAN_VERSION

    tm_version = TRANSFORMERMAN_VERSION
except ImportError:
    tm_version = ""


class TransformerManBaseDialog(QDialog):
    """Base dialog for TransformerMan with geometry saving/restoring."""

    def __init__(self, parent: QWidget | None, is_dark_mode: bool) -> None:
        """
        Initialize the base dialog.

        Args:
            parent: Parent widget (typically the main Anki window).
            is_dark_mode: Whether the UI is in dark mode.
        """
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        # Set the TransformerMan icon
        self.setWindowIcon(get_tm_icon(is_dark_mode))
        # Generate a unique geometry key based on the class name
        geometry_key = f"transformerman_{self.__class__.__name__}"
        restoreGeom(self, geometry_key)

    def set_title(self, title: str, add_version: bool = True) -> None:
        """Set the title of the dialog."""
        assert "TransformerMan" not in title
        title_prefix = "TransformerMan"
        if add_version and tm_version != "":
            title_prefix = f"{title_prefix} v{tm_version}"
        self.setWindowTitle(f"{title_prefix}: {title}")

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
