# Test Collections

This directory contains test collections used by TransformerMan's test suite.

## empty_collection

- **File**: `empty_collection/empty_collection.anki2`
- **Description**: A minimal Anki collection with no notes.
- **Contents**:
  - Notes: 0
  - Decks: 1 deck named "Default"
  - Models: Standard Anki models (Basic, Basic (and reversed card), Basic (optional reversed card), Basic (type in the answer), Cloze, Image Occlusion)
- **Purpose**: Used for tests that require a clean collection without any notes, allowing them to mock notes as needed.

## two_deck_collection

- **File**: `two_deck_collection/two_deck_collection.anki2`
- **Description**: A collection with two decks and 16 notes.
- **Contents**:
  - Notes: 16
  - Decks: "Default", "decka", "deckb"
  - Models: Basic, Basic (and reversed card), Basic (optional reversed card), Basic (type in the answer), Cloze
  - All notes use the "Basic" model with fields "Front" and "Back".
  - All fields are non‑empty (contain text).
  - Sample note IDs: 1701890133045, 1701890142102, 1701890146289, etc.
- **Purpose**: Used for tests that need a real collection with existing notes, e.g., validation of empty fields (since none are empty) or integration tests that can add temporary notes.

## Usage in Tests

Tests can use the `@with_test_collection("collection_name")` decorator together with the `test_collection` fixture to obtain a temporary copy of the collection. Each test receives its own isolated copy; modifications are discarded after the test.

## Full Note Dump

### empty_collection
No notes.

### two_deck_collection
All 16 notes use the "Basic" model with fields "Front" and "Back".

| Note ID | Front | Back |
|---------|-------|------|
| 1701890133045 | aaa car | aaa |
| 1701890142102 | aaa aa car | aaa |
| 1701890146289 | aaa aa car&nbsp;hello car | aaa |
| 1701890157782 | aaa aa car aaa hello car | aaa |
| 1701890173047 | bby bbb bbb hello | bbb |
| 1701890181405 | bby bbb bbb bbbbb hello | bbb hello |
| 1701890196332 | bby bbb bbb bbbbb bbbb | bbb bbb |
| 1701890395289 | bbbb bbbb bbb | bbb bbb |
| 1701890404845 | bbbb bbbb bbbb car bbb | bbb bbbbbb car bbb |
| 1701890410619 | bbbb bbbb bbbb bbb | bbb bbbbbb car&nbsp;bbb |
| 1701890435655 | aaaa&nbsp; hhh aaaa aaaa aa aa aaaa car | aa aa aa aa |
| 1701890440810 | aaaa aaaa aaaa aa aa aaaa car | aa aa aa aa |
| 1701890444014 | aaaa aaaa aaaa aa aa aaaa 3 | aa aa aa aa |
| 1701890446032 | aaaa aaaa hh aaaa aa aa aaaa 4 | aa aa aa aa hh |
| 1701890448066 | aaaa aaaa aaaa aa aa aaaa 5 | aa aa aa aa |
| 1701890458659 | aaaa aaaa aaaa aa aa aaaa 6 | aa aa aa aa |

## Maintenance

When adding new test collections, please update this file and ensure the collection is placed in its own subdirectory with a descriptive name. The collection file should be as small as possible to keep the repository lightweight.
