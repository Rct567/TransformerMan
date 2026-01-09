"""
Shared fixtures for UI tests.

This module provides common test fixtures for testing TransformerMan UI components.
Follows project guideline: "Use pytest fixtures, but try to use the real thing where possible (it often is)"
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from aqt.qt import QWidget, QMessageBox

from transformerman.lib.lm_clients import DummyLMClient, ApiKey, ModelName

if TYPE_CHECKING:
    from collections.abc import Generator
    from pytestqt.qtbot import QtBot


# Patch restoreGeom and saveGeom at the module level where they're used
# Also patch QMessageBox to avoid showing dialogs during tests
# Patch QueryOp to avoid requiring main window
@pytest.fixture(autouse=True)
def mock_anki_utils() -> Generator[None, None, None]:
    """Mock Anki utility functions that require main window."""
    with patch("transformerman.ui.base_dialog.restoreGeom") as mock_restore, \
         patch("transformerman.ui.base_dialog.saveGeom") as mock_save, \
         patch("transformerman.ui.settings_dialog.QMessageBox.question") as mock_qmessagebox, \
         patch("transformerman.ui.transform.preview_table.QueryOp") as mock_query_op:
        # Configure mocks to do nothing (successful no-op)
        mock_restore.return_value = None
        mock_save.return_value = None
        # Default QMessageBox.question to return Save to avoid blocking
        mock_qmessagebox.return_value = QMessageBox.StandardButton.Save

        # Mock QueryOp to avoid requiring main window
        mock_query_op_instance = Mock()
        mock_query_op_instance.failure.return_value = mock_query_op_instance
        mock_query_op_instance.run_in_background.return_value = None
        mock_query_op.return_value = mock_query_op_instance

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
def is_dark_mode() -> bool:
    """Fixture for dark mode setting."""
    return False
