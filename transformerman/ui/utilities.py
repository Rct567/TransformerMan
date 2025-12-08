"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from aqt.qt import QIcon

if TYPE_CHECKING:
    from aqt.qt import QAction, QMenu




def get_tm_icon(dark_mode: bool) -> QIcon:
    """Get the TransformerMan icon."""

    icon_folder = Path(__file__).parent.parent / "icons"

    if dark_mode:
        icon_path = icon_folder / "butterfly_solo_2_no_color_light.svg"
    else:
        icon_path = icon_folder / "butterfly_solo_2_no_color.svg"

    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


def insert_action_after(
    menu: QMenu,
    action_to_find: str,
    new_action: QAction,
    case_sensitive: bool = False,
) -> None:
    """
    Insert a new action into a menu after an existing action with matching text.

    Args:
        menu: The QMenu to insert the action into.
        action_to_find: Text to search for in existing menu actions.
        new_action: The new QAction to insert.
        case_sensitive: Whether the text search should be case sensitive.
    """
    # Find the target action
    target_action: Optional[QAction] = None
    for act in menu.actions():
        text = act.text()
        if text:
            search_text = text if case_sensitive else text.lower()
            find_text = action_to_find if case_sensitive else action_to_find.lower()
            if find_text in search_text:
                target_action = act
                break

    if target_action:
        # Insert after target action
        actions = menu.actions()
        try:
            target_index = actions.index(target_action)
            if target_index + 1 < len(actions):
                # Insert before the action that comes after target
                menu.insertAction(actions[target_index + 1], new_action)
            else:
                # Target is the last action, add at the end
                menu.addAction(new_action)
        except ValueError:
            # Should not happen since we found target_action, but fallback
            menu.addAction(new_action)
    else:
        # Target not found, add at the end
        menu.addAction(new_action)
