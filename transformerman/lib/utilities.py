from __future__ import annotations

import itertools
import sys
from typing import TYPE_CHECKING, Any, TypeVar

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