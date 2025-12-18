from __future__ import annotations

import itertools
import re
import sys
from typing import TYPE_CHECKING, Any

from typing import Callable
from typing_extensions import ParamSpec, TypeVar

from functools import wraps
from aqt.qt import QTimer

import inspect

if TYPE_CHECKING:
    from typing import Union
    from collections.abc import Iterable, Iterator
    from typing_extensions import TypeAlias
    JSON_TYPE: TypeAlias = Union[dict[str, "JSON_TYPE"], list["JSON_TYPE"], str, int, float, bool, None]
else:
    JSON_TYPE = Any


T = TypeVar('T')


# batched for Python < 3.12

if sys.version_info >= (3, 12):
    from itertools import batched as batched
else:

    def batched(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:
        """
        Batch an iterable into smaller batches of a specified size.

        Parameters:
            iterable (Iterable): The iterable to be batched.
            n (int): The size of each batch.

        Yields:
            tuple[T, ...]: A tuple of the batched elements.
        """

        it = iter(iterable)
        while True:
            batch = tuple(itertools.islice(it, n))
            if not batch:
                return
            yield batch


#  override decorator for Python < 3.12

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore[attr-defined]
elif TYPE_CHECKING:
    from typing_extensions import override
else:
    # Dummy decorator for runtime on Python < 3.12
    def override(func):  # type: ignore[misc]
        return func


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


def create_slug(text: str) -> str:
    """
    Create a URL-safe slug from a text string.
    
    Converts text to lowercase, replaces spaces and special characters with underscores,
    and removes consecutive underscores.
    
    Args:
        text: The text to convert to a slug
        
    Returns:
        A URL-safe slug string
        
    Example:
        >>> create_slug("My Field Name!")
        'my_field_name'
        >>> create_slug("Field  With   Spaces")
        'field_with_spaces'
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace spaces and non-alphanumeric characters with underscores
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    # Remove leading/trailing underscores
    slug = slug.strip('_')
    # Replace multiple consecutive underscores with a single one
    slug = re.sub(r'_+', '_', slug)
    return slug
