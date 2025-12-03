"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QPushButton,
    QWidget,
)

if TYPE_CHECKING:
    from ..lib.settings_manager import SettingsManager


class SettingsDialog(QDialog):
    """Settings dialog for TransformerMan plugin."""

    def __init__(self, parent: QWidget, settings_manager: SettingsManager) -> None:
        """
        Initialize the settings dialog.

        Args:
            parent: Parent widget.
            settings_manager: Settings manager instance.
        """
        super().__init__(parent)
        self.settings_manager = settings_manager

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        self.setWindowTitle("TransformerMan Settings")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        # API Key
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your API key...")
        api_key_layout.addWidget(self.api_key_input)
        layout.addLayout(api_key_layout)

        # Model Selection
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        model_layout.addWidget(self.model_combo)
        layout.addLayout(model_layout)

        # Batch Size
        batch_size_layout = QHBoxLayout()
        batch_size_layout.addWidget(QLabel("Batch Size:"))
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setMinimum(1)
        self.batch_size_spin.setMaximum(100)
        self.batch_size_spin.setValue(10)
        batch_size_layout.addWidget(self.batch_size_spin)
        layout.addLayout(batch_size_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _load_settings(self) -> None:
        """Load current settings into the UI."""
        # Load API key
        api_key = self.settings_manager.get_api_key()
        self.api_key_input.setText(api_key)

        # Load available models
        models = self.settings_manager.get_available_models()
        self.model_combo.addItems(models)

        # Select current model
        current_model = self.settings_manager.get_model()
        index = self.model_combo.findText(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

        # Load batch size
        batch_size = self.settings_manager.get_batch_size()
        self.batch_size_spin.setValue(batch_size)

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        # Save API key
        api_key = self.api_key_input.text().strip()
        self.settings_manager.set_api_key(api_key)

        # Save model
        model = self.model_combo.currentText()
        self.settings_manager.set_model(model)

        # Save batch size
        batch_size = self.batch_size_spin.value()
        self.settings_manager.set_batch_size(batch_size)

        self.accept()
