"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from pathlib import Path

from typing import Any, TYPE_CHECKING

from aqt import mw as anki_main_window, gui_hooks
from aqt.main import AnkiQt
from aqt.qt import QAction
from aqt.utils import showInfo, showWarning

from .transformerman.ui.main_window import TransformerManMainWindow # type: ignore[import-not-found]
from .transformerman.ui.settings_dialog import SettingsDialog # type: ignore[import-not-found]
from .transformerman.ui.utilities import insert_action_after, get_tm_icon # type: ignore[import-not-found]
from .transformerman.lib.addon_config import AddonConfig # type: ignore[import-not-found]


if TYPE_CHECKING:
    from aqt.browser.browser import Browser


def get_mw():
    return anki_main_window

mw = get_mw()

TM_ROOT_DIR = Path(__file__).parent
TM_USER_FILES_DIR = TM_ROOT_DIR / 'user_files'

if not TM_USER_FILES_DIR.is_dir():
    TM_USER_FILES_DIR.mkdir()

ADDON_NAME = "TransformerMan"


def open_settings(mw: AnkiQt, addon_config: AddonConfig) -> None:
    """Open the settings dialog."""

    addon_config.reload()

    dialog = SettingsDialog(mw, addon_config)
    dialog.exec()

def is_dark_mode(mw: AnkiQt) -> bool:
    # Detect dark mode
    return mw.app.styleSheet().lower().find("dark") != -1


def open_main_window(mw: AnkiQt, browser: Browser, addon_config: AddonConfig) -> None:
    """Open the main TransformerMan window from card browser."""
    if not mw.col:
        return

    # Get selected note IDs and card IDs
    note_ids = list(browser.selected_notes())
    card_ids = list(browser.selected_cards())

    if not note_ids:
        showInfo("Please select at least one note.", parent=browser)
        return

    addon_config.reload()

    if 'lm_client' not in addon_config:
        open_settings(mw, addon_config)
        return

    lm_client, error = addon_config.get_client()

    if lm_client is None:

        showWarning(
            f"{error}.\n\nPlease check your settings.",
            title="Configuration Error",
            parent=browser,
        )
        return

    window = TransformerManMainWindow(
        parent=browser,
        is_dark_mode=is_dark_mode(mw),
        col=mw.col,
        note_ids=note_ids,
        card_ids=card_ids,
        lm_client=lm_client,
        addon_config=addon_config,
        user_files_dir=TM_USER_FILES_DIR,
    )
    window.exec()


def setup_browser_menu(mw: AnkiQt, browser: Browser, menu: Any, addon_config: AddonConfig) -> None:
    """Add TransformerMan to browser context menu."""

    action = QAction(ADDON_NAME, browser)
    action.setIcon(get_tm_icon(is_dark_mode(mw)))
    action.triggered.connect(lambda: open_main_window(mw, browser, addon_config))
    menu.addAction(action)


def setup_browser_top_menu(mw: AnkiQt, browser: Browser, addon_config: AddonConfig) -> None:
    """Add TransformerMan as a clickable button in the Browser's menu bar."""
    menu_bar = browser.form.menubar
    if not menu_bar:
        return

    action = QAction(ADDON_NAME, browser)
    action.triggered.connect(lambda: open_main_window(mw, browser, addon_config))
    menu_bar.addAction(action)


# Add menu items
if mw:

    assert isinstance(mw, AnkiQt)

    addon_config = AddonConfig.from_anki_main_window(mw)
    addon_config.load()

    # Add settings to 'Tools' menu in main window
    settings_action = QAction(f"{ADDON_NAME}: API settings", mw)
    settings_action.setIcon(get_tm_icon(is_dark_mode(mw)))
    settings_action.triggered.connect(lambda: open_settings(mw, addon_config))

    # Use the utility function to insert after "Preferences"
    menu = mw.form.menuTools
    insert_action_after(menu, "Preferences", settings_action)

    # Add to browser context menu (right-click menu) in browser window
    gui_hooks.browser_will_show_context_menu.append(lambda browser, menu: setup_browser_menu(mw, browser, menu, addon_config))

    # Add to browser top menu bar in browser window
    if addon_config.is_enabled("show_tm_in_browser_top_menu", False):
        gui_hooks.browser_menus_did_init.append(lambda browser: setup_browser_top_menu(mw, browser, addon_config))
