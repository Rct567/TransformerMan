"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from pathlib import Path

from typing import Any, Optional, TYPE_CHECKING

from aqt import mw as anki_main_window, gui_hooks
from aqt.qt import QAction
from aqt.utils import showInfo

from .transformerman.ui.main_window import TransformerManMainWindow
from .transformerman.ui.settings_dialog import SettingsDialog
from .transformerman.lib.addon_config import AddonConfig


if TYPE_CHECKING:
    from aqt.main import AnkiQt
    from aqt.browser.browser import Browser


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
    addon_config = AddonConfig.from_anki_main_window(mw)


def open_settings() -> None:
    """Open the settings dialog."""
    if not mw:
        return

    addon_config.reload()

    dialog = SettingsDialog(mw, addon_config)
    dialog.exec()


def open_main_window(browser: Browser) -> None:
    """Open the main TransformerMan window from card browser."""
    if not mw or not mw.col:
        return

    # Get selected note IDs
    note_ids = list(browser.selected_notes())

    if not note_ids:
        showInfo("Please select at least one note.", parent=browser)
        return

    addon_config.reload()
    lm_client = addon_config.getClient()

    # Detect dark mode
    is_dark_mode = False
    if mw and mw.app:
        is_dark_mode = mw.app.styleSheet().lower().find("dark") != -1

    window = TransformerManMainWindow(
        parent=browser,
        is_dark_mode=is_dark_mode,
        col=mw.col,
        note_ids=note_ids,
        lm_client=lm_client,
        addon_config=addon_config,
        user_files_dir=TM_USER_FILES_DIR,
    )
    window.show()


def setup_browser_menu(browser: Browser, menu: Any) -> None:
    """Add TransformerMan to browser context menu."""
    action = QAction(ADDON_NAME, browser)
    action.triggered.connect(lambda: open_main_window(browser))
    menu.addAction(action)


def setup_browser_top_menu(browser: Browser) -> None:
    """Add TransformerMan as a clickable button in the Browser's menu bar."""
    # Create a clickable action (button) directly on the menu bar
    action = QAction(ADDON_NAME, browser)
    action.triggered.connect(lambda: open_main_window(browser))

    menu_bar = browser.form.menubar
    if not menu_bar:
        return

    menu_bar.addAction(action)


# Add menu items
if mw:
    # Add settings to Tools menu
    settings_action = QAction(f"{ADDON_NAME} Settings", mw)
    settings_action.triggered.connect(open_settings)
    mw.form.menuTools.addAction(settings_action)

    # Add to browser context menu (right-click menu)
    #gui_hooks.browser_will_show_context_menu.append(setup_browser_menu)

    # Add to browser top menu bar
    gui_hooks.browser_menus_did_init.append(setup_browser_top_menu)
