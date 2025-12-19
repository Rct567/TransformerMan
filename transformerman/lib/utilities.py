from __future__ import annotations

import itertools
import re
import sys
from typing import TYPE_CHECKING, Any


from typing_extensions import TypeVar


if TYPE_CHECKING:
    from typing import Union
    from collections.abc import Iterable, Iterator
    from typing_extensions import TypeAlias
    JSON_TYPE: TypeAlias = Union[dict[str, "JSON_TYPE"], list["JSON_TYPE"], str, int, float, bool, None]
else:
    JSON_TYPE = Any


T = TypeVar("T")


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



# create_slug function

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
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    # Remove leading/trailing underscores
    slug = slug.strip("_")
    # Replace multiple consecutive underscores with a single one
    slug = re.sub(r"_+", "_", slug)
    return slug
