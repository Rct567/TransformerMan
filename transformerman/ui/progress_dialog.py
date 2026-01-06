"""
TransformerMan by Rick Zuidhoek. Licensed under the GNU GPL-3.0.
See <https://www.gnu.org/licenses/gpl-3.0.html> for details.
"""

from __future__ import annotations

import re
import time

from aqt.qt import QProgressDialog, QTimer, QWidget, Qt

from ..lib.http_utils import LmRequestStage, LmProgressData


class ProgressDialog(QProgressDialog):
    """
    Custom progress dialog for transformation operations with intelligent wait messaging.

    Automatically switches from "Sending request..." to "Waiting for response... Xs"
    after a configurable threshold when the LM takes time to respond.
    """

    WAIT_THRESHOLD_SECONDS = 3

    def __init__(self, num_batches: int, parent: QWidget | None = None) -> None:
        """
        Initialize the progress dialog.

        Args:
            num_batches: Number of batches to process.
            parent: Parent widget.
        """
        # Use indeterminate/busy indicator for single batch, regular progress bar for multiple
        if num_batches == 1:
            super().__init__("Processing...", "Cancel", 0, 0, parent)
        else:
            super().__init__(f"Processing batch 0 of {num_batches}...", "Cancel", 0, num_batches, parent)

        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumDuration(0)
        self.setMinimumWidth(300)
        self.setAutoClose(False)
        self.setAutoReset(False)

        self._is_active = True
        self._cancel_requested = False
        self._current_stage: LmRequestStage | None = None
        self._sending_start_time: float | None = None

        # Timer for updating wait counter
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_wait_counter)
        self._timer.start(1000)

        # Connect cancel signal
        self.canceled.disconnect()
        self.canceled.connect(self._on_cancel)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self._cancel_requested = True
        self._timer.stop()
        self.setCancelButtonText(None)

    def is_cancel_requested(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_requested

    def update_progress(self, current_batch: int, total_batches: int, detailed: LmProgressData | None = None) -> None:
        """
        Update progress display with batch and detailed information.

        Args:
            current_batch: Current batch index (0-based).
            total_batches: Total number of batches.
            detailed: Optional detailed progress data from LM client.
        """
        if not self._is_active:
            return

        if detailed:
            if detailed.stage == LmRequestStage.RECEIVING:
                self._sending_start_time = None

        try:
            # Track stage and timing
            if detailed:
                if detailed.stage == LmRequestStage.SENDING and self._sending_start_time is None:
                    self._sending_start_time = time.time()
                self._current_stage = detailed.stage

            # Build progress message
            progress_msg: list[str] = []

            if self._cancel_requested:
                progress_msg.append("Processing canceled...")
            elif total_batches == 1:
                progress_msg.append("Processing...")
            else:
                progress_msg.append(f"Processing batch {current_batch + 1} of {total_batches}...")

            if detailed:
                detailed_msg = self._format_detailed_message(detailed)
                progress_msg.append(detailed_msg)

            self.setLabelText("\n".join(progress_msg))

            # Update progress value for multiple batches
            if total_batches > 1:
                self.setValue(current_batch)
        except RuntimeError:
            # Dialog already deleted
            pass

    def _format_detailed_message(self, data: LmProgressData) -> str:
        """
        Format detailed progress message for sending/receiving stages.

        Args:
            data: Progress data from LM client.

        Returns:
            Formatted message string.
        """
        if data.stage == LmRequestStage.SENDING:
            if self._should_show_wait_message():
                wait_seconds = self._get_wait_seconds()
                return f"Waiting for response... {wait_seconds}s"
            return "Sending request..."

        # RECEIVING stage
        size_kb = data.total_bytes / 1024
        speed_kb_s = (data.total_bytes / data.elapsed) / 1024 if data.elapsed > 0 else 0

        if not data.text_chunk:  # Download phase (non-SSE or before first chunk)
            if data.content_length:
                total_kb = data.content_length / 1024
                return f"Receiving response... ({size_kb:.0f} KB / {total_kb:.0f} KB at {speed_kb_s:.0f} KB/s)"
            return f"Receiving response... ({size_kb:.0f} KB at {speed_kb_s:.0f} KB/s)"

        # Streaming phase
        return f"Processing response... ({size_kb:.0f} KB at {speed_kb_s:.0f} KB/s)"

    def _should_show_wait_message(self) -> bool:
        """Determine if we should show the waiting message."""
        return (
            self._current_stage == LmRequestStage.SENDING
            and self._sending_start_time is not None
            and time.time() - self._sending_start_time > self.WAIT_THRESHOLD_SECONDS
        )

    def _get_wait_seconds(self) -> int:
        """Calculate seconds spent waiting beyond the threshold."""
        if not self._sending_start_time:
            return 0
        elapsed = time.time() - self._sending_start_time
        return max(0, int(elapsed - self.WAIT_THRESHOLD_SECONDS))

    def _update_wait_counter(self) -> None:
        """Update the wait counter in the progress label (called by timer)."""
        if not self._should_show_wait_message():
            return

        current_text = self.labelText()
        wait_seconds = self._get_wait_seconds()

        if "Waiting for response..." in current_text:
            # Update the existing counter
            new_text = re.sub(r"Waiting for response\.\.\. \d+s", f"Waiting for response... {wait_seconds}s", current_text)
            self.setLabelText(new_text)
        elif "Sending request..." in current_text:
            # Switch from sending to waiting
            new_text = current_text.replace("Sending request...", f"Waiting for response... {wait_seconds}s")
            self.setLabelText(new_text)

    def cleanup(self) -> None:
        """Clean up resources and close the dialog."""
        self._is_active = False
        self._timer.stop()
        try:
            self.close()
        except RuntimeError:
            pass
