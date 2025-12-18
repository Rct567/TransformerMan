"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.

See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import QLabel, QCheckBox, QLineEdit, QWidget, Qt, QMouseEvent, QObject, QEvent

from ..lib.utilities import override, create_slug
from ..ui.ui_utilities import debounce, EventManager, Event

if TYPE_CHECKING:
    from ..lib.addon_config import AddonConfig


class FieldSelectionChangedEvent(Event):
    pass


class FieldInstructionChangedEvent(Event):
    pass


class FieldWidget(QWidget):
    """Widget containing all UI elements for a single field."""

    def __init__(
        self,
        field_name: str,
        note_model_id: int,
        addon_config: AddonConfig,
        event_manager: EventManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self.note_model_id = note_model_id
        self.addon_config = addon_config
        self.event_manager = event_manager
        self.is_overwritable = False

        # Create widgets
        self.read_checkbox = QCheckBox()
        self.read_checkbox.setToolTip("Allow read (include field content in the prompt)")
        self.read_checkbox.stateChanged.connect(self._on_read_changed)

        self.writable_checkbox = QCheckBox()
        self.writable_checkbox.setToolTip("Allow write (allow this field to be filled). Click with CTRL to make overwritable (red).")
        self.writable_checkbox.stateChanged.connect(self._on_writable_changed)

        # Install event filter to capture CTRL+click
        self.writable_checkbox.installEventFilter(self)

        self.field_label = QLabel(field_name)

        self.instruction_input = QLineEdit()
        self.instruction_input.setPlaceholderText("Optional instructions for this field...")
        self.instruction_input.textChanged.connect(self._on_instruction_changed)

        # Initial state
        self.instruction_input.setEnabled(False)

        # Load saved instruction from config
        self._load_instruction()

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Filter events for the writable checkbox to detect CTRL+click (or shift or meta click on macOS)."""
        if a0 == self.writable_checkbox and a1 is not None and a1.type() == a1.Type.MouseButtonPress:
            if not isinstance(a1, QMouseEvent):
                return super().eventFilter(a0, a1)
            modifiers = a1.modifiers()
            if (modifiers & Qt.KeyboardModifier.ControlModifier) or (modifiers & Qt.KeyboardModifier.MetaModifier) or (modifiers & Qt.KeyboardModifier.ShiftModifier):
                # CTRL+click or meta+shift click: toggle overwritable state
                if self.writable_checkbox.isChecked():
                    # Currently checked: toggle between writable and overwritable
                    if self.is_overwritable:
                        # Currently overwritable (red) -> uncheck
                        self.set_overwritable(False)
                        self.writable_checkbox.setChecked(False)
                    else:
                        # Currently writable (normal) -> make overwritable (red)
                        self.set_overwritable(True)
                else:
                    # Currently unchecked -> check as overwritable (red) directly
                    self.set_overwritable(True)
                    self.writable_checkbox.setChecked(True)
                # Return True to indicate we've handled the event
                return True
        # Let the parent class handle other events
        return super().eventFilter(a0, a1)

    def _on_read_changed(self) -> None:
        """Handle read checkbox state change."""
        if not self.read_checkbox.isChecked():
            # If context unchecked, uncheck writable
            self.writable_checkbox.setChecked(False)
        self.instruction_input.setEnabled(self.read_checkbox.isChecked())
        self._update_instruction_styling()
        self.event_manager.dispatch(FieldSelectionChangedEvent())

    def _on_writable_changed(self) -> None:
        """Handle writable checkbox state change."""
        if self.writable_checkbox.isChecked():
            # If writable checked, check context
            self.read_checkbox.setChecked(True)
        else:
            # If writable unchecked, clear overwritable state
            self.set_overwritable(False)
        self._update_instruction_styling()
        self.event_manager.dispatch(FieldSelectionChangedEvent())

    @debounce(500)
    def _on_instruction_changed(self) -> None:
        """Handle instruction input text change."""
        self._save_instruction()
        self.event_manager.dispatch(FieldInstructionChangedEvent())

    def set_overwritable(self, overwritable: bool) -> None:
        """Set overwritable state and update visual appearance."""
        self.is_overwritable = overwritable
        if overwritable:
            self.field_label.setStyleSheet("color: red; font-weight: bold;")
            self.writable_checkbox.setToolTip("Overwritable (field will be filled even if already has content).")
        else:
            self.field_label.setStyleSheet("")
            self.writable_checkbox.setToolTip("Allow write (allow this field to be filled). Click with CTRL to make overwritable (red).")
        self._update_instruction_styling()

    def is_read_selected(self) -> bool:
        """Return True if context checkbox is checked."""
        return self.read_checkbox.isChecked()

    def is_writable(self) -> bool:
        """Return True if writable checkbox is checked and not overwritable."""
        return self.writable_checkbox.isChecked() and not self.is_overwritable

    def is_overwritable_selected(self) -> bool:
        """Return True if field is in overwritable state."""
        return self.writable_checkbox.isChecked() and self.is_overwritable

    def _update_instruction_styling(self) -> None:
        """Update instruction input text color based on field state."""
        if self.read_checkbox.isChecked() and not self.writable_checkbox.isChecked():
            # Read mode: context checked but not writable -> gray out text
            self.instruction_input.setStyleSheet("color: gray;")
        else:
            # Either disabled (context unchecked) or writable/overwritable -> normal styling
            self.instruction_input.setStyleSheet("")

    def get_instruction(self) -> str:
        """Get instruction text."""
        return self.instruction_input.text().strip()

    def set_instruction_enabled(self, enabled: bool) -> None:
        """Enable or disable instruction input."""
        self.instruction_input.setEnabled(enabled)

    def set_context_checked(self, checked: bool) -> None:
        """Set context checkbox state."""
        self.read_checkbox.setChecked(checked)

    def _get_config_key(self) -> str:
        """Get the config key for this field's instruction."""
        field_slug = create_slug(self.field_name)
        return f"field_instructions_{self.note_model_id}_{field_slug}"

    def _save_instruction(self) -> None:
        """Save field instruction to config."""
        if self.note_model_id == 0:
            return
        instruction = self.get_instruction()
        config_key = self._get_config_key()
        self.addon_config.update_setting(config_key, instruction)

    def _load_instruction(self) -> None:
        """Load field instruction from config."""
        if self.note_model_id == 0:
            return
        config_key = self._get_config_key()
        instruction = self.addon_config.get(config_key, "")
        if isinstance(instruction, str) and instruction:
            self.instruction_input.setText(instruction)


class FieldWidgets:
    """Manager for multiple FieldWidget instances."""

    def __init__(self) -> None:
        self.event_manager = EventManager()
        self._widgets: dict[str, FieldWidget] = {}

    def clear(self) -> None:
        """Clear all widgets."""
        self._widgets.clear()

    def add(self, field_name: str, widget: FieldWidget) -> None:
        """Add a widget."""
        self._widgets[field_name] = widget

    def items(self):
        """Return widget items."""
        return self._widgets.items()

    def values(self):
        """Return widget values."""
        return self._widgets.values()

    def __getitem__(self, key: str) -> FieldWidget:
        return self._widgets[key]

    def __contains__(self, key: str) -> bool:
        return key in self._widgets

    def __len__(self) -> int:
        return len(self._widgets)

    def get_selected_fields(self) -> list[str]:
        """Get the currently selected field names."""
        return [field_name for field_name, widget in self._widgets.items() if widget.is_read_selected()]

    def get_writable_fields(self) -> list[str]:
        """Get the currently selected writable field names (excluding overwritable fields)."""
        return [field_name for field_name, widget in self._widgets.items() if widget.is_writable()]

    def get_overwritable_fields(self) -> list[str]:
        """Get the currently selected overwritable field names."""
        return [field_name for field_name, widget in self._widgets.items() if widget.is_overwritable_selected()]

    def get_fillable_fields(self) -> list[str]:
        """Get all fields that can be filled (writable or overwritable)."""
        return [field_name for field_name, widget in self._widgets.items() if widget.is_writable() or widget.is_overwritable_selected()]

    def has_fillable_fields(self) -> bool:
        """Return True if any fillable fields are selected."""
        return len(self.get_fillable_fields()) > 0

    def get_current_field_instructions(self) -> dict[str, str]:
        """Get current field instructions for the selected fields."""
        selected_fields = self.get_selected_fields()
        return {field_name: widget.get_instruction() for field_name, widget in self._widgets.items() if widget.get_instruction() and field_name in selected_fields}
