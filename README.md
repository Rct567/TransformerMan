# TransformerMan

An Anki add-on that uses language models to intelligently fill empty fields in your notes based on context, examples, and custom instructions.

## Features

- 🤖 **AI-Powered Field Completion**: Automatically fill empty fields using language models
- 📝 **Context-Aware**: Uses example notes from your collection to guide the LM
- 🎯 **Selective Processing**: Choose which fields to fill and which note types to process
- 📋 **Custom Instructions**: Add field-specific instructions to guide the LM
- 📊 **Batch Processing**: Efficiently process large selections with progress tracking
- ⚙️ **Configurable**: Customize API settings, model selection, and batch size

## Installation

1. Download the latest release
2. Open Anki and go to **Tools → Add-ons**
3. Click **Install from file...** and select the downloaded file
4. Restart Anki

## Usage

### Quick Start

1. **Configure Settings** (first time only):
   - Go to **Tools → TransformerMan Settings**
   - Enter your API key (when using a real LM service)
   - Select your preferred model
   - Adjust batch size if needed (default: 10)

2. **Transform Notes**:
   - Open the card browser
   - Select one or more notes
   - Right-click and select **Edit → TransformerMan**
   - Choose the note type from the dropdown
   - Select which fields to fill
   - (Optional) Add custom instructions for specific fields
   - Click **Transform**

### Example Workflow

Let's say you have German vocabulary notes with "Front" (German word) and "Back" (English translation) fields:

1. Select notes where "Back" is empty
2. Open TransformerMan
3. Select the "Basic" note type
4. Check the "Back" field
5. Add instruction: "Provide a concise English translation"
6. Click Transform

The plugin will:
- Find 3 example notes with both fields filled
- Send them to the LM along with your notes
- Fill the empty "Back" fields with translations

## Configuration

### Settings

Access via **Tools → TransformerMan Settings**:

- **API Key**: Your language model API key
- **Model**: Choose from available models (GPT-4, Claude, etc.)
- **Batch Size**: Number of notes to process per batch (1-100)

### Default Configuration

The plugin comes with sensible defaults in `config.json`:

```json
{
    "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "model": "claude-v1.3-100k",
    "batch_size": 10
}
```

## How It Works

1. **Example Selection**: The plugin selects up to 3 example notes from your collection that:
   - Have the same note type
   - Have the most filled fields (in the selected field set)
   - Have the highest word count in those fields

2. **Prompt Construction**: Creates a structured prompt with:
   - Field-specific instructions (if provided)
   - Example notes in XML format
   - Target notes to fill

3. **LM Processing**: Sends the prompt to the language model and receives filled notes

4. **Note Updates**: Updates only the empty fields in the selected field set

## Development

### Current Implementation

The plugin currently uses a `DummyLMClient` that returns mock responses for testing. To integrate with a real LM service:

1. Create a new class extending `LMClient` in `transformerman/lib/lm_client.py`
2. Implement the `transform(prompt: str) -> str` method
3. Update `__init__.py` to use your client

### Running Tests

```bash
# Run all tests
pytest tests -v

# Run specific test file
pytest tests/test_lm_client.py -v

# Run with coverage
pytest tests --cov=transformerman --cov-report=html
```

### Type Checking

```bash
mypy transformerman tests
```

### Linting

```bash
ruff check transformerman tests
```

### Pre-commit Hook

A git pre-commit hook is included to automatically run code quality checks before committing. The hook script is located at `scripts/pre-commit-hook.sh`.

#### Installation

```bash
# Copy the hook to the git hooks directory
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

#### What the hook runs:
1. **pyright** - Type checking on staged Python files
2. **mypy** - Static type checking on staged Python files
3. **ruff check** - Linting on staged Python files
4. **pytest** - Full test suite (always runs)

#### Usage

```bash
# To temporarily bypass the hook:
git commit --no-verify -m "Your message"

# To remove the hook:
rm .git/hooks/pre-commit
```

#### Features
- Runs static analysis (pyright, mypy, ruff) only on staged Python files
- Always runs the full pytest test suite
- Stops the commit if any check fails
- Provides clear success/failure messages

## Project Structure

```
TransformerMan/
├── __init__.py                      # Plugin entry point
├── config.json                      # Default configuration
├── transformerman/
│   ├── lib/                        # Core library
│   │   ├── lm_client.py           # LM client abstraction
│   │   ├── prompt_builder.py      # Prompt construction
│   │   ├── xml_parser.py          # XML parsing
│   │   ├── selected_notes.py      # Note management
│   │   ├── settings_manager.py    # Settings management
│   │   └── transform_operations.py # Batch processing
│   └── ui/                         # User interface
│       ├── main_dialog.py         # Main dialog
│       └── settings_dialog.py     # Settings dialog
└── tests/                          # Test suite
```

## License

GNU GPL-3.0 - See LICENSE file for details

## Support

For issues, questions, or contributions, please visit the project repository.

## Roadmap

- [ ] Real LM API integration (OpenAI, Anthropic, Grok)
- [ ] Field validation before updating
- [ ] Enhanced error reporting and logging
- [ ] Undo support integration
- [ ] Example note preview/selection UI
- [ ] Token usage tracking and optimization
