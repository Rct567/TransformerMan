"""
Shared fixtures for UI tests.

This module provides common test fixtures for testing TransformerMan UI components.
Follows project guideline: "Use pytest fixtures, but try to use the real thing where possible (it often is)"
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

# Global patch for QueryOp in UI tests
import aqt.operations
from tests.conftest import FakeQueryOp
aqt.operations.QueryOp = FakeQueryOp  # type: ignore

# Global patch for showInfo and showWarning in UI tests
import aqt.utils
aqt.utils.showInfo = MagicMock()
aqt.utils.showWarning = MagicMock()

from aqt.qt import QWidget, QMessageBox

from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName
if TYPE_CHECKING:
    from collections.abc import Generator
    from pytestqt.qtbot import QtBot


@pytest.fixture(autouse=True)
def mock_anki_utils() -> Generator[None, None, None]:
    """Mock Anki utility functions that require main window."""
    with patch("transformerman.ui.base_dialog.restoreGeom") as mock_restore, \
         patch("transformerman.ui.base_dialog.saveGeom") as mock_save, \
         patch("transformerman.ui.settings_dialog.QMessageBox.question") as mock_qmessagebox:
        # Configure mocks to do nothing (successful no-op)
        mock_restore.return_value = None
        mock_save.return_value = None
        # Default QMessageBox.question to return Save to avoid blocking
        mock_qmessagebox.return_value = QMessageBox.StandardButton.Save

        yield


@pytest.fixture
def qtbot(qtbot: QtBot) -> QtBot:
    """QtBot fixture for testing Qt widgets."""
    return qtbot


@pytest.fixture
def parent_widget(qtbot: QtBot) -> QWidget:
    """Create a parent widget for dialogs."""
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def dummy_lm_client() -> DummyLMClient:
    """Real DummyLMClient instance for testing."""
    return DummyLMClient(ApiKey(""), ModelName("lorem_ipsum"))


@pytest.fixture
def mock_show_info() -> MagicMock:
    """Fixture to access and reset the global showInfo mock."""
    mock: MagicMock = aqt.utils.showInfo  # type: ignore
    mock.reset_mock()
    return mock


@pytest.fixture
def mock_show_warning() -> MagicMock:
    """Fixture to access and reset the global showWarning mock."""
    mock: MagicMock = aqt.utils.showWarning  # type: ignore
    mock.reset_mock()
    return mock


@pytest.fixture
def is_dark_mode() -> bool:
    """Fixture for dark mode setting."""
    return False
