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
    from ..lib.addon_config import AddonConfig

from ..lib.lm_clients import LM_CLIENTS, create_lm_client


class SettingsDialog(QDialog):
    """Settings dialog for TransformerMan plugin."""

    def __init__(self, parent: QWidget, addon_config: AddonConfig) -> None:
        """
        Initialize the settings dialog.

        Args:
            parent: Parent widget.
            addon_config: Addon configuration instance.
        """
        super().__init__(parent)
        self.addon_config = addon_config

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

        # LM Client Selection
        client_layout = QHBoxLayout()
        client_layout.addWidget(QLabel("LM Client:"))
        self.client_combo = QComboBox()
        self.client_combo.currentTextChanged.connect(self._on_client_changed)
        client_layout.addWidget(self.client_combo)
        layout.addLayout(client_layout)

        # Model Selection (appears after client selection)
        self.model_widget = QWidget()
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        model_layout.addWidget(self.model_combo)
        self.model_widget.setLayout(model_layout)
        self.model_widget.setVisible(False)
        layout.addWidget(self.model_widget)

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

        current_client = str(self.addon_config.get("lm_client", "dummy"))

        # Load API key for current client
        api_key = self.addon_config.get_api_key(current_client)
        self.api_key_input.setText(api_key)

        # Load LM clients
        clients = list(LM_CLIENTS.keys())
        self.client_combo.addItems(clients)
        current_client = str(self.addon_config.get("lm_client", "dummy"))
        idx_client = self.client_combo.findText(current_client)
        if idx_client >= 0:
            self.client_combo.setCurrentIndex(idx_client)
        self._populate_models_for_client(current_client)

        # Load batch size
        batch_size = self.addon_config.get("batch_size", 10)
        if isinstance(batch_size, int):
            self.batch_size_spin.setValue(batch_size)

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        # Get current client
        client_name = self.client_combo.currentText()

        # Save API key using AddonConfig's method
        api_key = self.api_key_input.text().strip()
        self.addon_config.set_api_key(client_name, api_key)

        # Save LM client
        self.addon_config.update_setting("lm_client", client_name)

        # Save model
        model = self.model_combo.currentText()
        self.addon_config.update_setting("model", model)

        # Save batch size
        batch_size = self.batch_size_spin.value()
        if batch_size < 1:
            batch_size = 1
        self.addon_config.update_setting("batch_size", batch_size)

        self.accept()

    def _on_client_changed(self, client_name: str) -> None:
        # Update API key field for the selected client
        api_key = self.addon_config.get_api_key(client_name)
        self.api_key_input.setText(api_key)
        self._populate_models_for_client(client_name)

    def _populate_models_for_client(self, client_name: str) -> None:
        # Get API key for this client
        api_key = self.addon_config.get_api_key(client_name)
        client = create_lm_client(client_name, api_key)
        models = client.get_available_models()
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            current_model = str(self.addon_config.get("model", "claude-v1.3-100k"))
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            self.model_widget.setVisible(True)
        else:
            self.model_widget.setVisible(False)
