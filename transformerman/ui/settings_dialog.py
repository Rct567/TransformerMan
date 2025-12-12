"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QWidget,
    QGroupBox,
    QSizePolicy,
    QFormLayout,
    Qt,
    QMessageBox,
    QCloseEvent,
)
from aqt.utils import showWarning

if TYPE_CHECKING:
    from ..lib.addon_config import AddonConfig

from ..lib.lm_clients import LM_CLIENTS, get_lm_client_class
from ..lib.utilities import override

from .base_dialog import TransformerManBaseDialog
from .custom_widgets import FormattedSpinBox


class SettingsDialog(TransformerManBaseDialog):
    """Settings dialog for TransformerMan plugin."""

    def __init__(self, parent: QWidget, addon_config: AddonConfig) -> None:
        """
        Initialize the settings dialog.

        Args:
            parent: Parent widget.
            addon_config: Addon configuration instance.
        """
        super().__init__(parent, True)
        self.addon_config = addon_config
        self._is_loading_settings = False  # Flag to prevent save button from enabling during initial setup

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Setup the UI components."""
        self.setWindowTitle("TransformerMan API Settings")
        self.setMinimumWidth(400)

        # Main layout with stretch to control resizing
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Create a group box for the form elements
        settings_group = QGroupBox("Settings")
        settings_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create a vertical layout for the group box
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)

        # Use QFormLayout for proper label-field alignment (like an invisible table)
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(10, 15, 10, 15)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # LM Client Selection
        self.client_combo = QComboBox()
        self.client_combo.currentTextChanged.connect(self._on_client_changed)
        form_layout.addRow("LM Client:", self.client_combo)

        # Model Selection
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self._on_setting_changed)
        form_layout.addRow("Model:", self.model_combo)

        # API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your API key...")
        self.api_key_input.textChanged.connect(self._on_setting_changed)
        form_layout.addRow("API Key:", self.api_key_input)

        # Max Prompt Size
        self.max_prompt_size_spin = FormattedSpinBox()
        self.max_prompt_size_spin.setMinimum(10_000)  # 10k characters minimum
        self.max_prompt_size_spin.setMaximum(1_000_000)  # 1M characters maximum
        self.max_prompt_size_spin.setValue(500_000)  # Default 500k characters
        self.max_prompt_size_spin.setSuffix(" characters")
        self.max_prompt_size_spin.setSingleStep(10_000)  # Step by 10k
        self.max_prompt_size_spin.valueChanged.connect(self._on_setting_changed)
        form_layout.addRow("Max Prompt Size:", self.max_prompt_size_spin)

        # Timeout
        self.timeout_spin = FormattedSpinBox()
        self.timeout_spin.setMinimum(60)  # 1 second minimum
        self.timeout_spin.setMaximum(600)  # 600 seconds (10 minutes) maximum
        self.timeout_spin.setValue(120)  # Default 120 seconds
        self.timeout_spin.setSuffix(" seconds")
        self.timeout_spin.setSingleStep(10)  # Step by 10 seconds
        self.timeout_spin.valueChanged.connect(self._on_setting_changed)
        form_layout.addRow("Timeout:", self.timeout_spin)

        # Add the form layout to the group layout
        group_layout.addLayout(form_layout)

        # Add stretch inside the group box (below the form elements)
        group_layout.addStretch(1)

        settings_group.setLayout(group_layout)
        main_layout.addWidget(settings_group)

        # Button layout with fixed size buttons aligned to right
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)  # Push buttons to the right

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save_clicked)
        self.save_button.setEnabled(False)
        self.save_button.setFixedWidth(80)
        self.save_button.setDefault(True)  # Make Save the default button

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        self.reset_button.setEnabled(False)
        self.reset_button.setFixedWidth(80)

        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.save_button)

        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def _load_settings(self) -> None:
        """Load current settings into the UI."""
        self._is_loading_settings = True

        current_client = str(self.addon_config.get("lm_client", "dummy"))

        # Check if the configured client is valid
        if current_client not in LM_CLIENTS:
            showWarning(
                f"Unknown LM client '{current_client}' configured. Resetting to 'dummy' client.",
                title="Configuration Warning",
                parent=self,
            )
            current_client = "dummy"
            self.addon_config.update_setting("lm_client", current_client)

        # Load API key for current client
        api_key = self.addon_config.get_api_key(current_client)
        self.api_key_input.setText(str(api_key))

        # Load LM clients
        clients = list(LM_CLIENTS.keys())
        self.client_combo.clear()
        self.client_combo.addItems(clients)

        idx_client = self.client_combo.findText(current_client)
        if idx_client >= 0:
            self.client_combo.setCurrentIndex(idx_client)
        self._populate_models_for_client(current_client)

        # Load max prompt size
        self.max_prompt_size_spin.setValue(self.addon_config.get_max_prompt_size())

        # Load timeout
        self.timeout_spin.setValue(self.addon_config.get_timeout())

        self._is_loading_settings = False

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

        # Save max prompt size
        max_prompt_size = self.max_prompt_size_spin.value()
        if max_prompt_size < 10_000:
            max_prompt_size = 10_000
        self.addon_config.update_setting("max_prompt_size", max_prompt_size)

        # Save timeout
        timeout = self.timeout_spin.value()
        if timeout < 1:
            timeout = 1
        self.addon_config.update_setting("timeout", timeout)

        # Disable save and reset buttons after saving
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)

    def _on_client_changed(self, client_name: str) -> None:
        # Update API key field for the selected client
        api_key = self.addon_config.get_api_key(client_name)
        self.api_key_input.setText(str(api_key))
        self._populate_models_for_client(client_name)

    def _on_setting_changed(self) -> None:
        # Enable save and reset buttons when settings are changed.
        if not self._is_loading_settings:
            self.save_button.setEnabled(True)
            self.reset_button.setEnabled(True)

    def _populate_models_for_client(self, client_name: str) -> None:
        client_class = get_lm_client_class(client_name)
        if client_class is None:
            models = []
        else:
            models = client_class.get_available_models()
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            current_model = str(self.addon_config.get("model", "claude-v1.3-100k"))
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        # Reload settings from config
        self.addon_config.reload()
        self._load_settings()

        # Disable save and reset buttons
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """
        Handle window close event.

        Show warning if there are unsaved changes.
        """
        if self.save_button.isEnabled():
            # There are unsaved changes
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. What would you like to do?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )

            if reply == QMessageBox.StandardButton.Save:
                # Save changes and close
                self._on_save_clicked()
                if a0:
                    a0.accept()
                # Call parent closeEvent to save geometry
                super().closeEvent(a0)
            elif reply == QMessageBox.StandardButton.Discard:
                # Discard changes and close
                if a0:
                    a0.accept()
                # Call parent closeEvent to save geometry
                super().closeEvent(a0)
            else:
                # Cancel close - don't save geometry since dialog isn't closing
                if a0:
                    a0.ignore()
        else:
            # No unsaved changes, proceed with close
            if a0:
                a0.accept()
            # Call parent closeEvent to save geometry
            super().closeEvent(a0)
