"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations


from typing import Callable, TYPE_CHECKING

from aqt.qt import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    Qt,
    QMouseEvent,
    QEnterEvent,
    QEvent,
    QCursor,
)

from dataclasses import dataclass

from ..lib.utilities import override
from .settings_dialog import SettingsDialog
from aqt.utils import showWarning

if TYPE_CHECKING:
    from ..lib.lm_clients import LMClient
    from ..lib.addon_config import AddonConfig


@dataclass
class StatKeyValue:
    """A stat with a display key and value."""
    key: str
    value: str = "-"
    visible: bool = True
    click_callback: Callable[[], None] | None = None


class StatContainer(QWidget):
    """A container widget for a single stat badge with optional click support."""

    def __init__(self, parent: QWidget | None, is_dark_mode: bool, stat: StatKeyValue) -> None:
        """Initialize the stat container."""
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.stat = stat
        self._is_clickable = stat.click_callback is not None
        self._hover_style = ""
        self._normal_style = ""

        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Ensure the widget shows its background from stylesheet
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)

        # Apply style immediately (before adding widgets)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self.key_label = QLabel(f"<span style='color: #888888;'>{stat.key}:</span>")
        self.value_label = QLabel(f"<b>{stat.value}</b>")

        self.key_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Make labels transparent so container background shows through
        self.key_label.setStyleSheet("background-color: transparent;")
        self.value_label.setStyleSheet("background-color: transparent;")

        layout.addWidget(self.key_label)
        layout.addWidget(self.value_label)

        self.setVisible(stat.visible)

    def _update_style(self) -> None:
        """Update the style based on clickability and dark mode."""
        bg_color = "#383838" if self.is_dark_mode else "#f0f0f0"
        hover_bg = "#484848" if self.is_dark_mode else "#e0e0e0"

        if self._is_clickable:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            style = (
                f"background-color: {bg_color}; "
                f"border-radius: 6px;"
            )
            hover_style = (
                f"background-color: {hover_bg}; "
                f"border-radius: 6px;"
            )
            self.setStyleSheet(style)
            self._hover_style = hover_style
            self._normal_style = style
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.setStyleSheet(f"background-color: {bg_color}; border-radius: 6px;")

    @override
    def enterEvent(self, event: QEnterEvent | None) -> None:
        """Handle mouse enter event for hover effect."""
        if self._is_clickable:
            self.setStyleSheet(self._hover_style)
        super().enterEvent(event)

    @override
    def leaveEvent(self, a0: QEvent | None) -> None:
        """Handle mouse leave event to reset hover effect."""
        if self._is_clickable:
            self.setStyleSheet(self._normal_style)
        super().leaveEvent(a0)

    @override
    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        """Handle mouse press event."""
        if a0 and self._is_clickable and a0.button() == Qt.MouseButton.LeftButton:
            if self.stat.click_callback:
                self.stat.click_callback()
        super().mousePressEvent(a0)

    def update_stat(self, stat: StatKeyValue) -> None:
        """Update the stat display and properties."""
        self.stat = stat
        self.key_label.setText(f"<span style='color: #888888;'>{stat.key}:</span>")
        self.value_label.setText(f"<b>{stat.value}</b>")
        self.setVisible(stat.visible)

        was_clickable = self._is_clickable
        self._is_clickable = stat.click_callback is not None
        if was_clickable != self._is_clickable:
            self._update_style()


class StatsWidget(QWidget):
    """A generic widget to display key-value pair statistics in styled badges."""

    def __init__(self, parent: QWidget | None, is_dark_mode: bool, init_stats: dict[str, StatKeyValue]) -> None:
        """Initialize the stats widget."""
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.stat_containers: dict[str, StatContainer] = {}
        self._setup_ui(init_stats)

    def _setup_ui(self, init_stats: dict[str, StatKeyValue]) -> None:
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 5, 0, 5)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.set_stats(init_stats)

        self.main_layout.addStretch()

    def set_stats(self, stats: dict[str, StatKeyValue]) -> None:
        """Set multiple stats at once."""
        for stat_id, stat in stats.items():
            self.set_stat(stat_id, stat)

    def set_stat(self, stat_id: str, stat: StatKeyValue) -> None:
        """Set up a single stat badge."""
        if stat_id in self.stat_containers:
            raise KeyError(f"Stat ID '{stat_id}' already exists in StatsWidget.")
        container = StatContainer(self, self.is_dark_mode, stat)
        self.stat_containers[stat_id] = container
        self.main_layout.addWidget(container)

    def update_stat(self, stat_id: str, stat: StatKeyValue) -> None:
        """Update a single stat badge."""
        if stat_id not in self.stat_containers:
            raise KeyError(f"Stat ID '{stat_id}' not found in StatsWidget.")
        self.stat_containers[stat_id].update_stat(stat)

    def update_stats(self, stats: dict[str, StatKeyValue]) -> None:
        """Update the values displayed in the badges."""
        for stat_id, stat in stats.items():
            self.update_stat(stat_id, stat)


def open_config_dialog(
    parent: QWidget,
    addon_config: AddonConfig,
    on_client_updated: Callable[[LMClient], None],
) -> None:
    """Open the addon configuration dialog."""
    SettingsDialog(parent=parent, addon_config=addon_config).exec()

    addon_config.reload()
    new_lm_client, error = addon_config.get_client()
    if error:
        showWarning(f"{error}.\n\nPlease check your settings.", title="Configuration Error", parent=parent)
        parent.close()
        return
    if new_lm_client:
        on_client_updated(new_lm_client)
