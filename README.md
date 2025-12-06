# TransformerMan

An Anki add-on that uses language models to intelligently fill empty fields in your notes based on context, examples, and custom instructions.

## Features

- 🤖 **AI-Powered Field Completion**: Automatically fill empty fields using language models
- 📝 **Context-Aware**: Uses example notes from your collection to guide the LM
- 🎯 **Selective Processing**: Choose which fields to fill and which note types to process
- 📋 **Custom Instructions**: Add field-specific instructions to guide the LM
- ⚙️ **Configurable**: Customize API settings, model selection, and batch size
- 🔍 **Preview Before Applying**: See what changes will be made before applying them
- ✅ **Multiple LM Support**: OpenAI (GPT-5, GPT-4o, o3), Claude, Gemini, DeepSeek, and Dummy client for testing

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
   - Adjust batch size if needed (default: 20)

2. **Transform Notes**:
   - Open the card browser
   - Select one or more notes
   - Right-click and select **Edit → TransformerMan** (or use the TransformerMan button in the menu bar)
   - Choose the note type from the dropdown
   - Select which fields to fill
   - (Optional) Add custom instructions for specific fields
   - Click **Preview** to see what changes will be made
   - Review the preview and click **Apply** to save changes

### Example Workflow

Let's say you have German vocabulary notes with "Front" (German word) and "Back" (English translation) fields:

1. Select notes where "Back" is empty
2. Open TransformerMan
3. Select the "Basic" note type
4. Check the "Back" field
5. Add instruction: "Provide a concise English translation"
6. Click Preview, then Apply

The plugin will:
- Find up to 3 example notes with both fields filled
- Send them to the LM along with your notes
- Fill the empty "Back" fields with translations
- Show a preview of changes before applying them

## Configuration

### Settings

Access via **Tools → TransformerMan Settings**:

- **API Key**: Your language model API key (required for real LM services)
- **Model**: Choose from available models (OpenAI GPT-5/4o, Claude, Gemini, DeepSeek, or Dummy for testing)
- **Batch Size**: Number of notes to process per batch (default: 20, range: 1-100)
- **Log LM Requests/Responses**: Enable logging for debugging (saved to user_files directory)


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

4. **Preview Display**: Shows what changes will be made with green highlighting

5. **Note Updates**: Updates only the empty fields in the selected field set (after user confirmation)

## Contributing

For development guidelines, testing instructions, and contribution information, please see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GNU GPL-3.0 - See LICENSE file for details

## Support

For issues, questions, or contributions, please visit the project repository.

## Roadmap

- [x] Preview before applying changes
- [x] Enhanced error reporting and logging
- [ ] Undo support integration
- [ ] Cost and token usage tracking and optimization
- [ ] Support for more LM providers
