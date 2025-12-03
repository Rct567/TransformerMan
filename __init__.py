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

from anki.collection import Collection



if TYPE_CHECKING:
    from aqt.deckbrowser import DeckBrowser, DeckBrowserContent
    from aqt.toolbar import Toolbar
    from .transformerman.lib.utilities import JSON_TYPE


def get_mw():
    return anki_main_window

mw: Optional[AnkiQt] = get_mw()

TM_ROOT_DIR = Path(__file__).parent
TM_USER_FILES_DIR = TM_ROOT_DIR / 'user_files'

if not TM_USER_FILES_DIR.is_dir():
    TM_USER_FILES_DIR.mkdir()


# use hooks to add menu options

