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


class StatsWidget(QWidget):
    """A generic widget to display key-value pair statistics in styled badges."""

    def __init__(self, parent: QWidget | None, is_dark_mode: bool, keys: list[str]) -> None:
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.stat_labels: dict[str, QLabel] = {}
        self._keys = keys
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 5, 0, 5)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Create persistent stat badges for each key
        for key in self._keys:
            container = QWidget()
            container.setFixedHeight(30)
            bg_color = "#383838" if self.is_dark_mode else "#f0f0f0"
            container.setStyleSheet(f"background-color: {bg_color}; border-radius: 6px;")

            c_layout = QHBoxLayout(container)
            c_layout.setContentsMargins(10, 0, 10, 0)
            c_layout.setSpacing(8)

            key_label = QLabel(f"<span style='color: #888888;'>{key}:</span>")
            val_label = QLabel("<b>-</b>")

            key_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            val_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            c_layout.addWidget(key_label)
            c_layout.addWidget(val_label)
            container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            self.stat_labels[key] = val_label
            self.main_layout.addWidget(container)

        self.main_layout.addStretch()

    def update_stats(self, stats: dict[str, str]) -> None:
        """
        Update the values displayed in the badges.

        Args:
            stats: A dictionary mapping keys to their new string values.
                   Values will be wrapped in <b> tags automatically.
        """
        for key, value in stats.items():
            if key in self.stat_labels:
                self.stat_labels[key].setText(f"<b>{value}</b>")
