"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from aqt.qt import QIcon

from typing import Callable
from typing_extensions import ParamSpec, Any

from functools import wraps
from aqt.qt import QTimer

import inspect

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


# debounce decorator for Qt6 functions

P = ParamSpec('P')


def debounce(wait_ms: int) -> Callable[[Callable[P, Any]], Callable[P, None]]:
    """
    Debounce decorator for Qt6 functions.

    Delays function execution until after `wait_ms` milliseconds have elapsed
    since the last time it was invoked. Automatically handles Qt signal arguments
    by matching them to the decorated function's signature.

    Args:
        wait_ms: The number of milliseconds to delay (must be an integer)

    Returns:
        A decorator that debounces the decorated function

    Example:
        @debounce(500)
        def on_text_changed(self, text: str) -> None:
            print(f"Processing: {text}")

        @debounce(500)
        def on_something_changed(self) -> None:
            # Signal arguments are automatically ignored
            print("Something changed")
    """
    def decorator(func: Callable[P, Any]) -> Callable[P, None]:
        timer: QTimer | None = None
        pending_call: tuple[tuple[Any, ...], dict[str, Any]] | None = None

        # Inspect the function signature to see how many parameters it accepts
        sig = inspect.signature(func)
        num_params = len(sig.parameters)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
            nonlocal timer, pending_call

            # Match arguments to function signature
            # If function expects fewer args than provided, trim the extras
            if len(args) > num_params:
                pending_call = (args[:num_params], kwargs)
            else:
                pending_call = (args, kwargs)

            # Stop existing timer if it's running
            if timer is not None and timer.isActive():
                timer.stop()

            # Create timer if needed
            if timer is None:
                timer = QTimer()
                timer.setSingleShot(True)

                def execute_pending() -> None:
                    if pending_call is not None:
                        call_args, call_kwargs = pending_call  # type: ignore[var-annotated]
                        func(*call_args, **call_kwargs)  # type: ignore[arg-type]

                timer.timeout.connect(execute_pending)

            # Start the timer (ensure wait_ms is an int)
            timer.start(int(wait_ms))

        return wrapper
    return decorator
