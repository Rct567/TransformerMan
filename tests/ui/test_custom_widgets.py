"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import QValidator

from transformerman.ui.custom_widgets import FormattedSpinBox

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestFormattedSpinBox:
    """Test suite for FormattedSpinBox widget."""

    def test_text_from_value_formats_with_underscores(self, qtbot: QtBot) -> None:
        """Test that textFromValue formats numbers with underscores."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)

        assert spin_box.textFromValue(1000) == "1_000"
        assert spin_box.textFromValue(10000) == "10_000"
        assert spin_box.textFromValue(100000) == "100_000"
        assert spin_box.textFromValue(1000000) == "1_000_000"

    def test_value_from_text_parses_underscores(self, qtbot: QtBot) -> None:
        """Test that valueFromText parses numbers with underscores."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)

        assert spin_box.valueFromText("1_000") == 1000
        assert spin_box.valueFromText("10_000") == 10000
        assert spin_box.valueFromText("100_000") == 100000
        assert spin_box.valueFromText("1_000_000") == 1000000

    def test_value_from_text_handles_plain_numbers(self, qtbot: QtBot) -> None:
        """Test that valueFromText handles plain numbers without underscores."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)

        assert spin_box.valueFromText("1000") == 1000
        assert spin_box.valueFromText("10000") == 10000

    def test_value_from_text_handles_suffix(self, qtbot: QtBot) -> None:
        """Test that valueFromText strips suffix before parsing."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setSuffix(" characters")

        assert spin_box.valueFromText("1_000 characters") == 1000
        assert spin_box.valueFromText("10_000 characters") == 10000
        assert spin_box.valueFromText("100 characters") == 100

    def test_value_from_text_handles_suffix_with_plain_numbers(self, qtbot: QtBot) -> None:
        """Test that valueFromText handles plain numbers with suffix."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setSuffix(" seconds")

        assert spin_box.valueFromText("60 seconds") == 60
        assert spin_box.valueFromText("120 seconds") == 120

    def test_validate_accepts_valid_input(self, qtbot: QtBot) -> None:
        """Test that validate accepts valid numeric input."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setMinimum(0)
        spin_box.setMaximum(1000)

        state, _text, _pos = spin_box.validate("100", 3)
        assert state == QValidator.State.Acceptable

        state, _text, _pos = spin_box.validate("1_000", 5)
        assert state == QValidator.State.Acceptable

    def test_validate_accepts_input_with_suffix(self, qtbot: QtBot) -> None:
        """Test that validate accepts input with suffix."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setMinimum(0)
        spin_box.setMaximum(1000)
        spin_box.setSuffix(" characters")

        state, _text, _pos = spin_box.validate("100 characters", 14)
        assert state == QValidator.State.Acceptable

        state, _text, _pos = spin_box.validate("500 characters", 14)
        assert state == QValidator.State.Acceptable

    def test_validate_rejects_invalid_input(self, qtbot: QtBot) -> None:
        """Test that validate rejects non-numeric input."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setMinimum(0)
        spin_box.setMaximum(1000)

        state, _text, _pos = spin_box.validate("abc", 3)
        assert state == QValidator.State.Invalid

    def test_validate_intermediate_for_out_of_range(self, qtbot: QtBot) -> None:
        """Test that validate returns intermediate for out-of-range values."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setMinimum(10)
        spin_box.setMaximum(100)

        state, _text, _pos = spin_box.validate("5", 1)
        assert state == QValidator.State.Intermediate

        state, _text, _pos = spin_box.validate("200", 3)
        assert state == QValidator.State.Intermediate

    def test_validate_intermediate_for_empty_input(self, qtbot: QtBot) -> None:
        """Test that validate returns intermediate for empty input."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)

        state, _text, _pos = spin_box.validate("", 0)
        assert state == QValidator.State.Intermediate

    def test_set_value_with_suffix(self, qtbot: QtBot) -> None:
        """Test that setValue works correctly with suffix set."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setSuffix(" examples")
        spin_box.setMinimum(0)
        spin_box.setMaximum(500)

        spin_box.setValue(100)
        assert spin_box.value() == 100
        assert "100" in spin_box.text()
        assert "examples" in spin_box.text()

    def test_typing_value_with_suffix_updates_correctly(self, qtbot: QtBot) -> None:
        """Test that typing a value with suffix updates the spinbox value."""
        spin_box = FormattedSpinBox()
        qtbot.addWidget(spin_box)
        spin_box.setSuffix(" seconds")
        spin_box.setMinimum(60)
        spin_box.setMaximum(600)
        spin_box.setValue(60)

        # Simulate typing "120 seconds"
        # The valueFromText should parse this correctly
        new_value = spin_box.valueFromText("120 seconds")
        assert new_value == 120

        # Verify validation accepts it
        state, _text, _pos = spin_box.validate("120 seconds", 11)
        assert state == QValidator.State.Acceptable
