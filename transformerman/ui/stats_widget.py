"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from aqt.qt import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    Qt,
)

from dataclasses import dataclass


@dataclass
class StatKeyValue:
    """A stat with a display key and value."""
    key: str
    value: str = "-"
    visible: bool = True


class StatsWidget(QWidget):
    """A generic widget to display key-value pair statistics in styled badges."""

    def __init__(self, parent: QWidget | None, is_dark_mode: bool, init_stats: dict[str, StatKeyValue]) -> None:
        """Initialize the stats widget."""
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.value_labels: dict[str, QLabel] = {}
        self.key_labels: dict[str, QLabel] = {}
        self.containers: dict[str, QWidget] = {}
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
        if stat_id in self.key_labels:
            raise KeyError(f"Stat ID '{stat_id}' already exists in StatsWidget.")
        container = QWidget()
        container.setFixedHeight(30)
        bg_color = "#383838" if self.is_dark_mode else "#f0f0f0"
        container.setStyleSheet(f"background-color: {bg_color}; border-radius: 6px;")

        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(10, 0, 10, 0)
        c_layout.setSpacing(8)

        key_label = QLabel(f"<span style='color: #888888;'>{stat.key}:</span>")
        val_label = QLabel(f"<b>{stat.value}</b>")

        key_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        val_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        c_layout.addWidget(key_label)
        c_layout.addWidget(val_label)
        container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.key_labels[stat_id] = key_label
        self.value_labels[stat_id] = val_label
        self.containers[stat_id] = container
        container.setVisible(stat.visible)
        self.main_layout.addWidget(container)

    def update_stat(self, stat_id: str, stat: StatKeyValue) -> None:
        """Update a single stat badge."""
        if stat_id not in self.key_labels or stat_id not in self.value_labels:
            raise KeyError(f"Stat ID '{stat_id}' not found in StatsWidget.")
        # Update the key label if display key changed
        self.key_labels[stat_id].setText(f"<span style='color: #888888;'>{stat.key}:</span>")
        # Update the value label
        self.value_labels[stat_id].setText(f"<b>{stat.value}</b>")
        # Update visibility
        if stat_id in self.containers:
            self.containers[stat_id].setVisible(stat.visible)

    def update_stats(self, stats: dict[str, StatKeyValue]) -> None:
        """Update the values displayed in the badges."""
        for stat_id, stat in stats.items():
            self.update_stat(stat_id, stat)
