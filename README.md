# TransformerMan

An Anki add-on that uses language models to intelligently fill empty fields in your notes based on context, examples, and custom instructions.

![TransformerMan](tranformerman_showcase_1.gif)


## Features

- 🤖 **AI-Powered Field Completion**: Fill empty fields in bulk using language models
- 📝 **Context-Aware**: Uses example notes from your collection to guide the LM
- 📋 **Custom Instructions**: Add field-specific instructions to guide the LM
- ⚙️ **Configurable**: Customize API settings, model selection, and prompt size
- 🔍 **Preview Before Applying**: See what changes will be made before applying them
- ✅ **Multiple LM Support**: Gemini, DeepSeek, Claude, OpenAI, and a Dummy client for testing

## Installation

1. Download the latest release from the [GitHub repository](https://github.com/Rct567/TransformerMan/releases)
2. Open Anki and go to **Tools → Add-ons**
3. Click **Install from file...** and select the downloaded `.ankiaddon` file
4. Restart Anki

## Usage

### Quick Start

1. **Configure Settings** (first time only):
   - Go to **Tools → TransformerMan Settings**
   - Enter your API key (when using a real LM service)
   - Select your preferred model

2. **Transform Notes**:
   - Open the card browser
   - Select one or more notes
   - Right-click and select **Edit → TransformerMan** (or use the TransformerMan button in the menu bar)
   - Choose the note type from the dropdown
   - Select which fields to fill
   - (Optional) Add custom instructions for specific fields
   - Click **Preview** to see what changes will be made
   - Review the preview and click **Apply** to save changes

## Configuration

### Settings

Access via **Tools → TransformerMan Settings**:

- **LM Client**: Choose from available language model clients (Dummy, OpenAI, Claude, Gemini, DeepSeek, OpenAI Custom)
- **Model**: Select model based on chosen client (e.g., OpenAI: GPT-4o/GPT-4o-mini/o1/o3 series, Claude: various models, etc.)
- **API Key**: Your language model API key (required for real LM services, not needed for Dummy client)
- **Max Prompt Size**: Maximum prompt size in characters (default: 100,000, range: 10,000-1,000,000)
- **Timeout**: Request timeout in seconds (default: 240, range: 60-600)
- **Max Examples**: Maximum number of example notes to use (default: 3, range: 0-500)
- **Custom Settings**: Client-specific settings (e.g., Organization ID for OpenAI)


## How It Works

1. **Note Selection**: Select notes in the Anki browser and open TransformerMan from the menu or right-click context menu

2. **Field Configuration**: For each field in your note type, you can:
   - **Context (read)**: Include field content in the prompt to provide context
   - **Writable (write)**: Allow the field to be filled (only empty fields by default)
   - **Overwritable**: Hold Ctrl+click on writable fields to allow overwriting existing content
   - **Instructions**: Add field-specific instructions to guide the LM

3. **Example Selection**: The plugin selects example notes from your collection (up to your configured "Max Examples" setting, default: 3) that:
   - Have the same note type
   - Have the most filled fields (in the selected field set)
   - Have the highest word count in those fields

4. **Batch Processing**: Notes are automatically batched based on your "Max Prompt Size" setting to optimize API usage and minimize costs

5. **Prompt Construction**: Creates structured prompts with:
   - Field-specific instructions (if provided)
   - Example notes in XML format
   - Target notes to fill

6. **LM Processing**: Sends batches to the language model and receives filled notes with progress tracking

7. **Preview Display**: Shows what changes will be made with green highlighting in a table format

8. **Note Updates**: Updates only the writable fields (empty by default, or overwritable if enabled) after user confirmation

## Contributing

For development guidelines, testing instructions, and contribution information, please see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GNU GPL-3.0 - See LICENSE file for details

## Support

For issues, questions, or contributions, please visit the project repository.

## Roadmap

- [x] Preview before applying changes
- [x] Settings dialog improvements (state management, first-open dialog)
- [x] Shift-click option for overwrite field checkbox
- [x] Configurable max examples setting
- [x] Undo support integration
- [x] Support for custom OpenAi endpoint
- [ ] Cost and token usage tracking and optimization
- [ ] Support for more LM providers
