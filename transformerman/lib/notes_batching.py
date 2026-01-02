"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations


import math
from typing import TYPE_CHECKING, Callable, NamedTuple

from .utilities import evenly_spaced_sample


if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence
    from anki.notes import Note
    from .selected_notes import SelectedNotesBatch, SelectedNotesFromType
    from ..ui.field_widgets import FieldSelection
    from .prompt_builder import PromptBuilder


class BatchingStats(NamedTuple):
    num_prompts_tried: int
    median_batch_size: int | None
    avg_batch_size: int | None
    num_batches: int
    num_notes_selected: int
    avg_note_size: int
    max_prompt_size: int


def predict_batch_size(max_prompt_size: int, num_notes_selected: int, avg_note_size: float) -> int:
    """
    Batch size prediction using continuous mathematical formula.

    Returns:
        Predicted batch size (notes per batch) to use as starting point
    """
    # Per-note overhead for metadata, separators, formatting
    overhead = 15
    # Base efficiency: increases with note size using smooth exponential curve
    # Approaches ~49% for very large notes, starts at ~31% for very small notes
    # The larger the note, the less the fixed overhead matters
    base_efficiency = 0.49 - 0.18 * math.exp(-avg_note_size / 530)
    # Prompt size scaling: larger prompts are more efficient
    # Use square root scaling for smooth, modest gains
    prompt_scale = math.sqrt(max_prompt_size / 100000)
    # Clamp to reasonable bounds (0.8x to 1.25x)
    prompt_scale = max(0.80, min(1.25, prompt_scale))
    # Combined efficiency with conservative multiplier
    # 0.80 multiplier makes predictions ~20% more pessimistic
    # This targets the lower of median/avg batch size
    efficiency = base_efficiency * prompt_scale * 0.80
    # Calculate total effective size with overhead
    effective_size_per_note = avg_note_size + overhead
    total_effective_size = num_notes_selected * effective_size_per_note
    # Calculate usable prompt space
    usable_prompt_size = max_prompt_size * efficiency
    # Calculate batches needed (minimum 1)
    batches = max(1, math.ceil(total_effective_size / usable_prompt_size))
    # Return the batch SIZE (notes per batch), not number of batches
    batch_size = max(1, num_notes_selected // batches)
    return batch_size


def find_adaptive_batch_size(
    total_items: int,
    predicted_size: int,
    validate_fn: Callable[[int], bool],
    accuracy_factor: float = 1.0,
) -> tuple[int, float]:
    """
    Find optimal batch size using adaptive prediction with learning.

    Uses exponential growth/shrinkage to find the maximum valid batch size,
    starting from a predicted size. Learns from the result to improve future
    predictions via an accuracy factor.

    Algorithm:
    1. Apply accuracy factor to prediction
    2. Test batch size with validate_fn
    3. If valid: exponentially grow by 20% until invalid or exhausted
    4. If invalid: exponentially shrink by 30% until valid
    5. Calculate accuracy factor: 0.9 * old + 0.1 * (actual / predicted)

    Args:
        total_items: Total number of items available to batch
        predicted_size: Initial prediction for batch size (before adjustment)
        validate_fn: Function that returns True if batch size is valid/fits
        accuracy_factor: Learning factor from previous batches (default: 1.0)

    Returns:
        Tuple of (optimal_batch_size, updated_accuracy_factor)

    Example:
        >>> def fits(size: int) -> bool:
        ...     return build_prompt(notes[:size]) <= max_chars
        >>>
        >>> accuracy = 1.0
        >>> size, accuracy = find_adaptive_batch_size(100, 50, fits, accuracy)
        >>> # Use size for first batch, then use updated accuracy for next batch
    """
    if total_items <= 0:
        return 0, accuracy_factor

    # Apply learned accuracy adjustment
    adjusted_prediction = max(1, int(predicted_size * accuracy_factor))
    current_size = adjusted_prediction
    last_valid_size: int | None = None

    # Exponential search with growth/shrinkage
    while current_size > 0 and current_size <= total_items:
        is_valid = validate_fn(current_size)

        if is_valid:
            last_valid_size = current_size
            # Try growing (but cautiously)
            if current_size == total_items:
                break
            next_size = min(total_items, int(current_size * 1.2))
            if next_size == current_size:
                break
            current_size = next_size
        else:
            # Too large, shrink
            if last_valid_size is not None:
                current_size = last_valid_size
                break
            current_size = int(current_size * 0.7)

    # Final batch size
    batch_size = last_valid_size if last_valid_size is not None else max(1, current_size)

    # Update accuracy factor using exponential moving average
    if predicted_size > 0:
        new_accuracy = 0.9 * accuracy_factor + 0.1 * (batch_size / predicted_size)
    else:
        new_accuracy = accuracy_factor

    return batch_size, new_accuracy


def batched_by_prompt_size(
    notes_with_fields: SelectedNotesFromType,
    prompt_builder: PromptBuilder,
    field_selection: FieldSelection,
    max_chars: int,
    max_examples: int,
    logger: logging.Logger,
) -> tuple[list[SelectedNotesBatch], BatchingStats]:
    """
    Batch notes by maximum prompt size using adaptive prediction with learning.

    See find_adaptive_batch_size() for algorithm details.
    """

    # Get note objects
    notes = list(notes_with_fields.get_notes())

    num_prompts_tried = 0

    def build_prompt(test_selected_notes: SelectedNotesFromType) -> str:
        nonlocal num_prompts_tried
        num_prompts_tried += 1
        return prompt_builder.build_prompt(
            target_notes=test_selected_notes,
            field_selection=field_selection,
            max_examples=max_examples,
        )

    def create_validator(notes_list: Sequence[Note]) -> Callable[[int], bool]:
        def validate(size: int) -> bool:
            if size == 0:
                return True
            test_batch = notes_list[:size]
            test_selected_notes = notes_with_fields.new_selected_notes([note.id for note in test_batch])
            prompt = build_prompt(test_selected_notes)
            return len(prompt) <= max_chars

        return validate

    def calc_avg_note_size(notes_list: Sequence[Note], field_names: Sequence[str]) -> int:
        sample = evenly_spaced_sample(notes_list, 4000)
        avg_size = sum(sum(len(note[fields_name]) for fields_name in field_names) for note in sample) // len(sample)
        return avg_size

    batches: list[SelectedNotesBatch] = []
    remaining = notes.copy()
    accuracy_factor = 1.0
    avg_note_size = calc_avg_note_size(remaining, field_selection.selected)
    init_predicted = predict_batch_size(max_chars, len(remaining), avg_note_size)

    while remaining:

        # Predict batch size based on previous batches
        if len(batches) > 0:
            current_avg_batch_size = sum(len(batch) for batch in batches) // len(batches)
            predicted = current_avg_batch_size
        else:
            predicted = init_predicted

        # Find optimal size with adaptive learning
        validate_fn = create_validator(remaining)

        batch_size, accuracy_factor = find_adaptive_batch_size(
            total_items=len(remaining),
            predicted_size=predicted,
            validate_fn=validate_fn,
            accuracy_factor=accuracy_factor,
        )

        if predicted <= 1 and batch_size == 1:
            note = remaining[0]
            prompt_size = len(build_prompt(notes_with_fields.new_selected_notes([note.id])))
            if prompt_size > max_chars:
                logger.warning(
                    f"Note {note.id} exceeds maximum prompt size ({prompt_size} > {max_chars}). Skipping."
                )
                break

        # Create batch
        batch_notes = remaining[:batch_size]
        batch_note_ids = [note.id for note in batch_notes]
        batches.append(notes_with_fields.new_selected_notes_batch(batch_note_ids))
        remaining = remaining[batch_size:]

    # Calculate and store stats
    num_batches = len(batches)
    if batches:
        median_batch_size = sorted(len(batch) for batch in batches)[num_batches // 2]
        avg_batch_size = sum(len(batch) for batch in batches) // num_batches
    else:
        median_batch_size = None
        avg_batch_size = None
        logger.info("No batches created!")

    batching_stats = BatchingStats(
        num_prompts_tried=num_prompts_tried,
        median_batch_size=median_batch_size,
        avg_batch_size=avg_batch_size,
        num_batches=num_batches,
        num_notes_selected=len(notes),
        avg_note_size=avg_note_size,
        max_prompt_size=max_chars
    )

    return batches, batching_stats
