**Task: Develop an Anki Plugin Called "TransformerMan"**

You are tasked with creating an Anki add-on (plugin) that enables users to transform the content of selected notes using a language model (LM). The plugin should integrate seamlessly with Anki's card browser and use an LM (e.g., via API like OpenAI or Grok) to fill in empty fields based on examples, field names, deck names, and optional user instructions.

### User Workflow
1. **Selection and Activation**: The user selects one or more cards in Anki's card browser, right-clicks, and selects "TransformerMan" from the context menu.
2. **Dialog Window**: A new dialog window opens with the following GUI elements:
   - A dropdown menu listing available note types (models) from the selected cards, sorted by frequency of occurrence (most common first). Pre-select the most frequent note type.
   - A text label displaying the number of selected notes (e.g., "X notes selected"). After selecting a note type, update this to reflect only the notes matching that type.
   - A section displaying all fields of the selected note type as checkboxes (allow selection/deselection). By default, select the first two fields if available.
     - For each selected field, include an adjacent text input box where the user can enter optional instructions for the LM (e.g., "Make this field concise and in bullet points").
   - A "Transform" button. When clicked, initiate the transformation process (described below) on the filtered notes. Include a progress indicator during processing.

### Transformation Process
- **Overview**: For the selected notes (filtered by the chosen note type) and fields, use an LM to fill in empty fields. The LM prompt should be dynamically generated based on user inputs.
- **LM Prompt Construction**:
  - Base the prompt on: field names, full deck name, and any user-provided instructions per field.
  - Goal: Instruct the LM to (1) fill empty selected fields intelligently (e.g., infer content from context like field name and deck name), and (2) adhere to any user instructions for that field.
  - Include up to 3 example notes (of the same note type) with existing content:
    - Select examples from the user's collection (prioritizing those matching the selected deck if possible).
    - Prioritize by: (1) Number of selected fields that are non-empty (higher first), then (2) total word count in those fields (higher first).
    - If fewer than 3 examples exist, use what's available.
  - After examples, provide the target notes (including all fields, even empty ones) and ask the LM to respond with the same notes but with the specified empty fields filled.
- **Data Handling**:
  - Process notes in batches if needed to avoid LM token limits.
  - Update the original notes in Anki with the LM-generated content (only in selected fields that were empty).
  - Handle errors gracefully (e.g., show a dialog if LM API fails or if no fields are selected).
- **XML-Like Data Structure for LM Prompt**:
  Use this structured format for examples and target notes in the LM prompt:

  ```
  <notes model="NOTE_TYPE_NAME">
  <note nid="NOTE_ID" deck="FULL_DECK_NAME">
  <field name="FIELD_NAME_1">CONTENT_OR_EMPTY</field>
  <field name="FIELD_NAME_2">CONTENT_OR_EMPTY</field>
  <!-- Additional fields as needed -->
  </note>
  <!-- Additional notes as needed -->
  </notes>
  ```

  Example of a supplied note block in the prompt (for a note to be filled):

  ```
  <notes model="Basic (front and back)">
  <note nid="34897752443" deck="German::recognition - Sentences">
  <field name="Front">Wie geht es dir?</field>
  <field name="Back"></field>
  </note>
  </notes>
  ```

- **LM Response Parsing**: Expect the LM to return the filled notes in the same XML-like format. Parse it to extract and apply changes to Anki notes.

### OOP Design
Structure the plugin using object-oriented principles for better organization. Suggested classes to create/include:
- **TransformerManMainDialog**: A GUI class (extending Qt dialog) managing the dialog window shown when the user has selected notes/cards and right clicked on "TransformerMan".
- **SelectedNotes**: A class responsible for selecting examples, batching notes, and updating Anki notes after transformation.
- **PromptBuilder**: A utility class to construct the LM prompt dynamically, including examples and target notes in the XML-like format.
- **LMClient**: A class for interacting with the external LM API (e.g., sending prompts, parsing responses). Make it configurable for different APIs. Use a dummy reponse for now.
- **AddonConfig**: A class to handle plugin settings (e.g., API keys, model selection) via Anki's config system.
- **SettingsDialog**: A GUI class for the plugin settings.

### Testing

Use Pytest and create tests for every major class and every major operation.

### Technical Requirements
- **Anki Integration**: Use Anki's API for accessing notes, fields, decks, and the card browser context menu.
  - **Example Imports**:
    ```python
    from anki.collection import Collection, OpChanges
    from anki.notes import Note, NoteId
    from anki.models import NotetypeId, NotetypeDict
    from anki.cards import CardId
	from aqt.taskman import TaskManager
    ```
- **LM Integration**: Assume an external LM API (e.g., configurable via plugin settings). Include a settings dialog for API key and model selection.
- **Edge Cases**: Handle very large selections (e.g., batch processing), empty user instructions (default to basic filling), or no eligible examples (proceed without them).

### Code examples:

```python
# Add menu items
settings_action = QAction(f"{ADDON_NAME} Settings", mw)
settings_action.triggered.connect(open_settings)
mw.form.menuTools.addAction(settings_action)```

```

```python
from aqt import mw
from aqt.operations import CollectionOp

op = CollectionOp(
        parent=mw,
        op=lambda col: batch_modify_notes(col, note_ids, new_value),
        success=on_success
    )
    op.run_in_background()
```

```python
from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Callable, Set
from dataclasses import dataclass

from aqt.operations import QueryOp
from aqt.utils import showInfo, tooltip
from aqt.qt import QProgressDialog, QWidget, Qt

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import NoteId
    from .lm_clients import LMClient
    from .prompt_builder import PromptBuilder


@dataclass
class BatchResult:
    """Result from processing a batch."""
    updated_fields: int
    failed_notes: list[NoteId]
    error: str | None = None


def transform_notes_with_progress(
    parent: QWidget,
    col: Collection,
    batches: list[list[NoteId]],
    lm_client: LMClient,
    prompt_builder: PromptBuilder,
    selected_fields: Set[str],
) -> None:
    """Transform notes in batches with progress tracking."""

    total_batches = len(batches)
    progress = QProgressDialog(
        f"Processing batch 0 of {total_batches}...",
        "Cancel",
        0,
        total_batches,
        parent,
    )
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)  # Show immediately
    progress.show()

    def process_batches(col: Collection) -> dict[str, int]:
        """Background operation that processes each batch."""
        total_updated = 0
        total_failed = 0
        batch_idx = 0

        for batch_idx, note_ids in enumerate(batches):
            if progress.wasCanceled():
                break

            # Update progress dialog
            progress.setLabelText(f"Processing batch {batch_idx + 1} of {total_batches}...")
            progress.setValue(batch_idx)

            try:
                notes = [col.get_note(nid) for nid in note_ids]
                prompt = prompt_builder.build_prompt(col, notes, selected_fields)
                response = lm_client.transform(prompt)
                field_updates = parse_xml_response(response)

                for nid in note_ids:
                    note = col.get_note(nid)
                    updates = field_updates.get(str(nid), {})

                    for field_name, content in updates.items():
                        if field_name in selected_fields and not note[field_name].strip():
                            note[field_name] = content
                            total_updated += 1

                    col.update_note(note)

            except Exception as e:
                print(f"Error processing batch {batch_idx}: {e}")
                total_failed += len(note_ids)
                continue

        progress.setValue(total_batches)

        return {
            "updated": total_updated,
            "failed": total_failed,
            "batches_processed": batch_idx + 1 if not progress.wasCanceled() else batch_idx,
        }

    def on_success(results: dict[str, int]) -> None:
        progress.close()
        message = "Transformation complete!\n\n"
        message += f"Batches processed: {results['batches_processed']}/{total_batches}\n"
        message += f"Fields updated: {results['updated']}\n"
        if results['failed'] > 0:
            message += f"Failed notes: {results['failed']}"
        tooltip(message)

    def on_failure(exc: Exception) -> None:
        progress.close()
        showInfo(f"Error during transformation: {exc!s}")

    QueryOp(
        parent=parent,
        op=lambda col: process_batches(col),
        success=on_success,
    ).failure(on_failure).run_in_background()
```

