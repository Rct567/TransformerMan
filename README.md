# TransformerMan

An Anki add-on that uses LM's to intelligently __fill empty fields__ based on context, examples, and custom instructions.

![TransformerMan](tranformerman_showcase_1.gif)


## Features

- 🤖 **AI-Powered Field Completion**: Fill empty fields in bulk using language models
- 📝 **Context-Aware**: Automatically uses related notes as examples
- 📋 **Custom Instructions**: Add field-specific instructions to guide the LM
- 🔍 **Preview Before Applying**: See what changes will be made before applying them
- ✅ **Multiple LM Support**: Gemini, DeepSeek, Claude, OpenAI, and a Dummy client for testing

## Use Cases

- 🌍 **Translation**: Translate text from one field to another in any language
- 🧠 **Mnemonics**: Create memory aids and associations to help retention
- 🎨 **Visual Content**: Generate SVG images to visualize concepts
- 📚 **Definitions & Examples**: Fill in explanations, examples, or clarifications
- 🏷️ **Classification**: Tag, annotate or categorize learning material
- 📦 **Deck Standardization**: Fill missing information in decks you've downloaded or imported
- ❓ **Active Recall**: Generate cloze deletions or question-answer pairs from content

## Installation

To download this add-on, please copy and paste the following code into Anki (**Tools > Add-ons > Get Add-ons...**):
__1033047802__

## Usage

### Quick Start

1. **Configure Settings** (first time only):
   - Go to **Tools → TransformerMan Settings**
   - Select a LM Client (e.g., Gemini, DeepSeek)
   - Enter your API key (if needed)
   - Select your preferred model

2. **Transform Notes**:
   - Open the card browser
   - Select one or more notes
   - Right-click and select **TransformerMan**
   - Select which fields to include via the "__Read__" checkbox
   - Click the "__Write__" checkbox to allow writing to the field
   - CTRL or shift click on the "__Write__" checkbox to allow overwriting existing content
   - (Optional) Add custom instructions for specific fields
   - Click **Preview** to see what changes will be made
   - Review the changes and click **Apply** to save changes

Note: You can hold shift and click on "Preview" to view and change the generated prompt.

## Free Options

- **Gemini**: Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- **LM Studio**: Download [LM Studio](https://lmstudio.ai/), run local LLMs like gpt-oss, Qwen3, DeepSeek on your computer.
- **DeepSeek**: Free tier with generous limits, get API key from [DeepSeek Platform](https://platform.deepseek.com/)
- **Groq**: Free tier available with rate limits, get API key from [Groq Console](https://console.groq.com/)

## Configuration

### Settings

Access via **Tools → TransformerMan Settings**:

- **LM Client**: Choose from available language model clients (Dummy, OpenAI, Claude, Gemini, DeepSeek, OpenAI Custom)
- **Model**: Select model based on chosen client (e.g., OpenAI: GPT-4o/GPT-4o-mini/o1/o3 series, Claude: various models, etc.)
- **API Key**: Your language model API key
- **Max Prompt Size**: Maximum prompt size in characters (lower number would require more batches)
- **Timeout**: Request timeout in seconds
- **Max Notes Per Batch**: Maximum number of notes to process in a single batch
- **Max Examples**: Maximum number of example notes to use for generated prompt
- **Custom Settings**: Client-specific settings (e.g., Organization ID for OpenAI)

Note: both **Max Prompt Size** and **Max Notes Per Batch** limit the number of notes processed in a single batch, and thus the amount of API calls needed.

## How It Works

1. **Note Selection**: Select notes in the Anki browser and open TransformerMan from the menu or right-click context menu

2. **Field Configuration**: For each field in your note type, you can:
   - **Context (read)**: Include field in the prompt to provide context
   - **Writable (write)**: Allow empty fields to be filled
   - **Overwritable**: Ctrl+click on 'Write' checkbox to allow overwriting existing content
   - **Instructions**: Add field-specific instructions to guide the LM

3. **Example Selection**: The plugin selects example notes from your collection (up to your configured "Max Examples" setting) that:
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

8. **Note Updates**: Updates notes after user confirmation

## Contributing

For development guidelines, testing instructions, and contribution information, please see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GNU GPL-3.0 - See LICENSE file for details

## Support

For issues, questions, or contributions, please visit the project repository.
