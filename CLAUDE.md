# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

M4A-Transcriber-TW is a professional, cross-platform audio transcription and translation tool that converts audio files to Traditional Chinese (Taiwan) text. It uses OpenAI's Whisper API for transcription and GPT-4o for intelligent translation and text refinement.

**Version:** 3.0 (October 2025)

**Key Features:**
- Multi-format audio support (M4A, MP3, WAV, FLAC, AAC)
- ⭐ Advanced audio filtering with full GUI control (NEW in v3.0)
- ⭐ Cross-platform FFmpeg auto-detection (NEW in v3.0)
- ⭐ Voice frequency enhancement (300-3400Hz) (NEW in v3.0)
- Automatic audio chunking for large files
- Parallel processing of audio chunks
- ⭐ GPT-5 powered translation with smart role switching (UPGRADED in v3.0)
- Both CLI and GUI interfaces with comprehensive error handling

## Architecture

### Core Components

1. **AudioProcessor** (`app.py`): The main processing engine
   - Handles all audio transcription logic
   - Manages OpenAI API interactions
   - Implements audio filtering, splitting, and noise reduction
   - Processes files in parallel using ThreadPoolExecutor

2. **TranscriptionApp** (`gui_app.py`): GUI application
   - Tkinter-based graphical interface
   - Delegates all processing to AudioProcessor
   - Manages user settings and displays results
   - Provides real-time logging and progress tracking

### Processing Pipeline

```
Audio Input → Filter Audio → Split to Chunks → Parallel Transcription (Whisper)
→ Noise Text Filtering → GPT Translation → Merge Results → Text Output
```

**Important:** The GUI is a thin wrapper around AudioProcessor. All business logic lives in `app.py`, including:
- Audio filtering parameters (high-pass, low-pass, compression)
- Chunk splitting logic (default 15MB chunks)
- Whisper transcription with custom prompts
- GPT translation with customizable system prompts
- Noise text filtering using regex patterns

## Common Commands

### Running the Application

```bash
# GUI mode (recommended for users)
python gui_app.py

# CLI mode (for automation/scripting)
python app.py
```

### Development Setup

```bash
# Install dependencies
pip install -r requirments.txt

# Note: The file is named "requirments.txt" (typo in original)
# On Linux, FFmpeg is required at: /usr/bin/ffmpeg and /usr/bin/ffprobe

# Set up API key in .env file
echo "OPENAI_API_KEY=your_key_here" > .env
```

### Testing

There are no automated tests in this repository. To test:
1. Place audio files in `./speech/` directory
2. Run the application and verify output in `./text/` directory

## Key Configuration

### Audio Processing Parameters (v3.0 - Fully Configurable in GUI)

Default values defined in `AudioProcessor.filter_audio()`:

- **Audio directories**: `./speech` (input), `./text` (output)
- **Chunk size**: 15MB max per API call (adjustable 5-25MB)
- **High-pass filter**: 80Hz (removes low-frequency noise) - GUI adjustable 0-500Hz
- **Low-pass filter**: 8000Hz (preserves speech spectrum) - GUI adjustable 3000-20000Hz
- **Target volume**: -20.0dBFS - GUI adjustable -30.0 to -10.0dBFS
- **Compression ratio**: 3.0 - GUI adjustable 1.0-10.0
- **Noise reduction**: Enabled by default - GUI toggle
- ⭐ **Voice boost** (NEW): Enabled by default - Enhances 300-3400Hz range - GUI toggle

### FFmpeg Configuration (v3.0 - Full Cross-Platform with macOS Enhancement)

- **Cross-platform support**: Uses `shutil.which()` to auto-detect FFmpeg on all platforms
- **macOS-specific enhancements** (NEW):
  - Checks multiple Homebrew installation paths:
    1. `/opt/homebrew/bin/ffmpeg` (M1/M2/M3 - Apple Silicon)
    2. `/usr/local/bin/ffmpeg` (Intel Mac)
    3. `/usr/bin/ffmpeg` (system default)
  - Automatically uses the first found path
- **Fallback logic**:
  - Windows: `ffmpeg.exe` / `ffprobe.exe` (requires PATH setup)
  - macOS: Tries multiple Homebrew paths with helpful installation instructions
  - Linux: `/usr/bin/ffmpeg` / `/usr/bin/ffprobe`
- **Logging**: Reports detected paths and provides platform-specific installation guidance

### Whisper Transcription

- Model: `whisper-1`
- Accepts custom prompts for specialized vocabulary/names
- Transcribes to original language first (usually English or mixed)

### GPT Translation (v3.0 - Updated with Smart Role Switching)

- ⭐ Model: `gpt-5` (default, latest flagship model)
- **Smart role switching**: Automatically selects correct API role based on model
  - GPT-5 / o1 / o3 series → `"developer"` role
  - GPT-4o / GPT-4.1 / GPT-4 → `"system"` role
- Model parameter is configurable via function argument
- Supports multiple models: gpt-5, gpt-4o, gpt-4o-mini, gpt-4.1
- Default task: Translate to Traditional Chinese (Taiwan), correct errors, deduplicate, segment logically
- Improved error handling with model-specific messages

## Working with the Code

### Modifying Audio Processing

Audio processing parameters are in `AudioProcessor.filter_audio()` at app.py:42-98. To adjust filtering:
- Modify parameters in method signature
- Update `gui_app.py` defaults loading in `_load_defaults()` if needed

### Customizing Translation

GPT system prompt is defined in two places:
1. Default in `app.py` at translate_to_chinese_with_gpt() (lines 149-201)
2. GUI default loaded from inspection in `gui_app.py` (lines 52-68)

To change translation behavior, modify the system prompt text.

### Adding New Audio Formats

1. Add file extension to filters in `gui_app.py`:
   - Line 518: `add_input_files()` filetypes
   - Line 531: `add_input_folder()` audio_extensions

2. Ensure FFmpeg supports the format (most common formats already work)

## Important Implementation Details

### Parallel Processing

- Uses `ThreadPoolExecutor` with max_workers=2 for chunk processing
- Each chunk is transcribed independently then merged in order
- Results stored in array by index to maintain proper sequence

### Temporary File Management

- Audio chunks are exported as `.mp3` files during processing
- Cleanup happens in `finally` block at app.py:364-380
- Ensures temporary files are deleted even on errors

### Logging System

- Uses Python's `logging` module
- GUI captures logs via custom `GuiLogHandler` class
- Logs display real-time in GUI and can be saved

### API Key Management

- Stored in `.env` file in project root
- GUI provides save/load functionality
- Loaded via `python-dotenv` package

## Common Gotchas (v3.0 - Many Issues Fixed!)

1. ✅ **FFmpeg paths** (FIXED in v3.0): Now uses automatic cross-platform detection via `shutil.which()`. macOS supports both Intel and Apple Silicon Homebrew paths. See `app.py:37-101`.

2. ✅ **GPT Model & Role** (CORRECTED in v3.0):
   - Default model: `gpt-5` (not gpt-4o)
   - **Smart role switching**: Automatically uses correct role based on model
   - GPT-5/o1/o3 → `"developer"` role
   - GPT-4o/GPT-4.1 → `"system"` role
   - See `app.py:214-291`

3. ✅ **Requirements file** (FIXED in v3.0): Renamed from "requirments.txt" to "requirements.txt" with proper encoding.

4. **Noise filtering** uses extensive regex patterns (app.py:238-366). Be careful when modifying as it affects all transcription results. These patterns are well-tested.

5. **Whisper prompt integration**: The whisper_prompt parameter helps with specialized vocabulary but doesn't guarantee correct recognition of all terms.

6. ⭐ **Audio filter parameters** (NEW in v3.0): The `filter_audio()` method now accepts **kwargs, allowing GUI to pass custom parameters. Always use keyword arguments when calling.

7. ⭐ **GUI state management** (IMPROVED in v3.0): The GUI now uses `should_stop` flag for reliable cancellation. Thread safety improved with proper `root.after()` calls.

8. **GUI validation** (NEW in v3.0): Start transcription now validates file existence, write permissions, and API key before beginning processing.

## Version 3.0 Changes Summary

### Files Modified
- `app.py`: FFmpeg auto-detection, GPT-4o model, enhanced audio filtering, **kwargs support
- `gui_app.py`: Audio parameter controls, validation, error handling, stop functionality
- `requirements.txt`: Fixed encoding and filename
- `.gitignore`: Comprehensive patterns for Python, IDEs, temp files
- `README.md`: Updated features, troubleshooting, v3.0 changelog
- `CLAUDE.md`: This file, updated with v3.0 information

### Key API Changes (Backward Compatible)
- `AudioProcessor.filter_audio()`: Added `voice_boost` parameter (default=True)
- `AudioProcessor.split_audio()`: Now accepts **filter_params
- `AudioProcessor.process_files()`: Now accepts **audio_filter_params
- `AudioProcessor.translate_to_chinese_with_gpt()`:
  - Changed default `model` parameter to `"gpt-5"` (was gpt-4o)
  - **NEW**: Automatically selects correct role (`developer` or `system`) based on model
  - Supports gpt-5, gpt-4o, gpt-4o-mini, gpt-4.1, o1, o3 series

### Testing Recommendations
1. Test FFmpeg detection on Windows/macOS/Linux
2. Verify audio filtering with custom parameters
3. Test GUI stop button during processing
4. Verify validation catches missing files and permission errors
5. Test error handling when individual files fail

## File Structure (v3.0)

```
M4A-Transcriber-TW/
├── app.py                  # Core AudioProcessor class (CLI entry point) - UPDATED v3.0
├── gui_app.py              # GUI application (delegates to AudioProcessor) - UPDATED v3.0
├── requirements.txt        # Python dependencies - FIXED filename & encoding v3.0
├── requirments.txt.old     # Old requirements file (preserved for reference)
├── .env                    # OpenAI API key (not in git, user-created)
├── .gitignore             # Comprehensive ignore patterns - UPDATED v3.0
├── speech/                # Input audio files directory
│   ├── *.m4a, *.mp3, etc  # (gitignored)
│   └── OLD/               # Archive folder
├── text/                  # Output transcription files directory
│   ├── *.txt              # (gitignored)
│   └── OLD/               # Archive folder
├── docs/                  # Documentation and images
│   └── images/            # GUI screenshots
├── __pycache__/           # Python cache (gitignored) - NEW v3.0
├── README.md              # User documentation - UPDATED v3.0
├── CLAUDE.md              # This file - Developer guide - UPDATED v3.0
└── LICENSE                # MIT License
```

---

**Last Updated:** October 29, 2025
**Version:** 3.0
**Maintainer:** Sheng1111
