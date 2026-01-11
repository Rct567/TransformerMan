from __future__ import annotations

import io
import cProfile
from contextlib import contextmanager
from pathlib import Path
import pstats
import random

import itertools
import re
import sys
from typing import TYPE_CHECKING, Any

from typing_extensions import TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Union, IO
    from collections.abc import Iterable, Iterator, Sequence
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
    from typing_extensions import override  # type: ignore[unused-import]
else:
    # Dummy decorator for runtime on Python < 3.12
    def override(func: Callable) -> Callable[..., Any]:
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


# evenly_spaced_sample function


def evenly_spaced_sample(lst: Sequence[T], sample_size: int) -> Sequence[T]:
    """Select evenly spaced items from a list."""
    if sample_size >= len(lst):
        return lst
    step: float = len(lst) / sample_size
    return [lst[int(i * step)] for i in range(sample_size)]


# profiling


@contextmanager
def profile_context(amount: int = 40) -> Iterator[cProfile.Profile]:

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        yield profiler
    finally:
        profiler.disable()

        def print_results(output: IO[Any], sort_key: pstats.SortKey) -> None:
            ps = pstats.Stats(profiler, stream=output).sort_stats(sort_key)
            ps.print_callers(amount)
            output.write("\n\n-------------------------------------------------\n\n\n")
            ps.print_stats(amount)
            output.write("\n\n================================================\n\n\n\n")

        output = io.StringIO()
        print_results(output, pstats.SortKey.CUMULATIVE)
        print_results(output, pstats.SortKey.TIME)
        profiling_results = output.getvalue()

        dump_file = Path(__file__).parent.parent.parent / "profiling_results.txt"
        with dump_file.open("w", encoding="utf-8") as f:
            f.write(profiling_results)


# Lorem Ipsum generation

LOREM_WORDS: list[str] = [
    "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing",
    "elit", "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore",
    "et", "dolore", "magna", "aliqua", "enim", "ad", "minim", "veniam",
    "quis", "nostrud", "exercitation", "ullamco", "laboris", "nisi", "aliquip",
    "ex", "ea", "commodo", "consequat", "duis", "aute", "irure", "in",
    "reprehenderit", "voluptate", "velit", "esse", "cillum", "fugiat",
    "nulla", "pariatur", "excepteur", "sint", "occaecat", "cupidatat",
    "non", "proident", "sunt", "culpa", "qui", "officia", "deserunt",
    "mollit", "anim", "id", "est", "laborum"
]


def get_lorem_sentences_generator(
    num_sentences: int = 1,
    words_per_sentence: int | tuple[int, int] = 10
) -> Callable[[], str]:
    """
    Create a lorem sentence generator function.

    Args:
        num_sentences: Number of sentences to generate per call
        words_per_sentence: Approximate words per sentence

    Returns:
        A callable that generates deterministic lorem sentences
    """
    seed = 0

    def generate() -> str:
        nonlocal seed
        rng = random.Random(seed)

        if isinstance(words_per_sentence, tuple):
            word_count = rng.randint(*words_per_sentence)
        else:
            word_count = words_per_sentence

        sentences: list[str] = []
        for _ in range(num_sentences):
            words = rng.choices(LOREM_WORDS, k=word_count)
            sentence = " ".join(words)
            sentence = sentence[0].upper() + sentence[1:] + "."
            sentences.append(sentence)

        seed += 1
        return " ".join(sentences)

    return generate


def is_lorem_ipsum_text(text: str, min_words: int = 5) -> bool:
    words = [word.strip(".,!?") for word in text.lower().split()]
    if len(words) < min_words:
        return False
    for word in words:
        if not word in LOREM_WORDS:
            return False
    return True
