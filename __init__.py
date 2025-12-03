"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from pathlib import Path

from functools import partial
from typing import Any, NamedTuple, Optional, Callable, TYPE_CHECKING


from aqt.main import AnkiQt
from aqt import mw as anki_main_window, gui_hooks, dialogs
from aqt.qt import QAction

from anki.collection import Collection


if TYPE_CHECKING:
    from aqt.deckbrowser import DeckBrowser, DeckBrowserContent
    from aqt.toolbar import Toolbar
    from aqt.browser import Browser
    from .transformerman.lib.utilities import JSON_TYPE


def get_mw():
    return anki_main_window

mw: Optional[AnkiQt] = get_mw()

TM_ROOT_DIR = Path(__file__).parent
TM_USER_FILES_DIR = TM_ROOT_DIR / 'user_files'

if not TM_USER_FILES_DIR.is_dir():
    TM_USER_FILES_DIR.mkdir()

ADDON_NAME = "TransformerMan"

# Initialize settings
if mw:
    from transformerman.lib.addon_config import AddonConfig
    from transformerman.lib.settings_manager import SettingsManager
    from transformerman.lib.lm_client import DummyLMClient

    addon_config = AddonConfig.from_anki_main_window(mw)
    settings_manager = SettingsManager(addon_config)
    lm_client = DummyLMClient()


def open_settings() -> None:
    """Open the settings dialog."""
    if not mw:
        return

    from transformerman.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(mw, settings_manager)
    dialog.exec()


def open_main_dialog(browser: Browser) -> None:
    """Open the main TransformerMan dialog from card browser."""
    if not mw:
        return

    # Get selected note IDs
    note_ids = browser.selected_notes()

    if not note_ids:
        from aqt.utils import showInfo
        showInfo("Please select at least one note.")
        return

    from transformerman.ui.main_dialog import TransformerManMainDialog

    dialog = TransformerManMainDialog(
        parent=browser,
        col=mw.col,
        note_ids=note_ids,
        lm_client=lm_client,
        settings_manager=settings_manager,
    )
    dialog.exec()


def setup_browser_menu(browser: Browser) -> None:
    """Add TransformerMan to browser context menu."""
    action = QAction(ADDON_NAME, browser)
    action.triggered.connect(lambda: open_main_dialog(browser))
    browser.form.menuEdit.addAction(action)


# Add menu items
if mw:
    # Add settings to Tools menu
    settings_action = QAction(f"{ADDON_NAME} Settings", mw)
    settings_action.triggered.connect(open_settings)
    mw.form.menuTools.addAction(settings_action)

    # Add to browser menu
    gui_hooks.browser_menus_did_init.append(setup_browser_menu)

