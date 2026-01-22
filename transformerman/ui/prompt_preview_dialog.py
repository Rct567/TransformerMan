"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QLabel,
    QWidget,
)


class PromptPreviewDialog(QDialog):
    """Dialog for previewing and editing the prompt template."""

    def __init__(self, parent: QWidget, prompt_template: str, instruction: str | None = None) -> None:
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            prompt_template: The initial prompt template string.
            instruction: Optional instruction text to display.
        """
        super().__init__(parent)
        self.setWindowTitle("Prompt Preview")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self.prompt_template = prompt_template
        self.instruction = instruction
        self.modified_template: str | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Instructions
        layout.addWidget(QLabel("You can modify the prompt template below before it is sent to the model."))
        if self.instruction:
            layout.addWidget(QLabel(self.instruction))

        # Text area
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(self.prompt_template)
        layout.addWidget(self.text_edit)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.continue_button = QPushButton("Continue")
        self.continue_button.setDefault(True)
        self.continue_button.clicked.connect(self._on_continue)
        button_layout.addWidget(self.continue_button)

        layout.addLayout(button_layout)

    def _on_continue(self) -> None:
        """Handle continue button click."""
        self.modified_template = self.text_edit.toPlainText()
        self.accept()

    def get_template(self) -> str | None:
        """Return the modified template if accepted, else None."""
        if self.result() == QDialog.DialogCode.Accepted:
            return self.modified_template
        return None
