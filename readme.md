# VoiceScribe

[English](readme.md) | [繁體中文](README.zh-TW.md)

VoiceScribe is a multilingual audio transcription and faithful translation tool built on the OpenAI API. It provides both a command-line interface and a Tkinter desktop GUI. Translation defaults to Traditional Chinese for Taiwan (`zh-TW`), while any valid BCP 47 target language tag can be supplied by the user.

Current version: `2.4.3`

## Highlights

- Transcribes audio with OpenAI `gpt-transcribe` by default.
- Translates with `gpt-5.6-luna` and the Responses API, using `reasoning.effort="none"`.
- Supports configurable translation targets such as `zh-TW`, `en`, `ja`, `ko`, and `pt-BR`.
- Provides a transcript-only mode that skips translation and its associated API cost.
- Enforces a segment-level output contract so missing IDs, omitted content, and invalid responses never become the final result.
- Resumes completed transcription and translation work when source files and settings have not changed.
- Processes long recordings through low-memory FFmpeg segmentation instead of loading the entire file into Python memory.
- Supports M4A, MP3, WAV, FLAC, AAC, MP4, MPEG, and WebM.
- Stores every source file in a separate output directory with raw text, final text, cached segments, and a processing manifest.

## Requirements

- Python 3.10 or newer
- FFmpeg and FFprobe on `PATH`
- An OpenAI API key

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt -U
```

Install FFmpeg on macOS:

```bash
brew install ffmpeg
```

Install FFmpeg on Ubuntu or Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

On Windows, install FFmpeg and add both `ffmpeg` and `ffprobe` to `PATH`.

## API key

Copy the environment template and add your key:

```bash
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
```

The `.env` file stays local and is ignored by Git. If a key has ever been committed, revoke it on the OpenAI platform and create a replacement.

## Desktop GUI

```bash
python gui_app.py
```

The workspace includes:

- A batch queue for individual files or recursively discovered folders.
- API key, output directory, model, language, terminology, context, and performance settings.
- An editable target-language selector with common BCP 47 language tags.
- A **Transcript only** option that bypasses translation.
- A final-result preview, activity log, progress indicator, cancellation, and resumable processing.

The core fidelity prompt is protected. Recording context, preferred terminology, and style preferences are treated as low-priority data and cannot turn the task into a summary or omit source content.

## Command line

Process one or more files:

```bash
python app.py speech/meeting.m4a speech/interview.mp3
```

Process a directory recursively:

```bash
python app.py ./recordings --output-dir ./text
```

Translate into Japanese:

```bash
python app.py speech/meeting.m4a --target-language ja
```

Provide expected source languages, terminology, and recording context:

```bash
python app.py speech/meeting.m4a \
  --language zh \
  --language en \
  --keyword OpenAI \
  --keyword "Responses API" \
  --context "A bilingual technical meeting"
```

Create only a transcript and skip translation:

```bash
python app.py speech/meeting.m4a --transcript-only
```

`--language` is a repeatable hint describing languages expected in the audio. `--target-language` selects the single translation target and defaults to `zh-TW`.

Run `python app.py --help` for every option. When no input is supplied, VoiceScribe scans `speech/` recursively. The default output root is `text/`.

## Output structure

Each source gets its own directory:

```text
text/
└── meeting/
    ├── final.txt
    ├── raw.txt
    ├── manifest.json
    └── chunks/
        ├── a0000.raw.txt
        ├── a0001.raw.txt
        ├── s00001.zh-TW.txt
        └── s00002.zh-TW.txt
```

- `raw.txt` contains the merged transcript in audio-chunk order.
- `final.txt` contains the validated translation, or the transcript when transcript-only mode is enabled.
- `manifest.json` records source hashes, settings, mode, language, models, status, and errors.
- `chunks/` contains resumable audio-chunk transcripts and translated text segments.

If two sources have the same filename but different content, VoiceScribe adds a source-hash suffix instead of overwriting the existing job.

## Resuming and failure behavior

- Matching source and ASR settings reuse the raw transcript.
- Translation-only setting changes preserve the raw transcript and rerun only translation.
- Changing the target language invalidates translation cache without retranscribing the audio.
- Switching between translated and transcript-only output cannot reuse an incompatible `final.txt`.
- Timeouts, HTTP 429 responses, and server errors are retried up to three times by default.
- Final files use atomic replacement. Failed, cancelled, incomplete, or empty translation results do not overwrite a previous successful result.
- Temporary audio files are cleaned up after both success and failure.

## Models and language options

| Purpose | Default |
| --- | --- |
| Transcription | `gpt-transcribe` |
| Translation | `gpt-5.6-luna` |
| Target language | `zh-TW` |
| Reasoning effort | `none` |
| Text verbosity | `high` |

Supported transcription models:

- `gpt-transcribe`
- `gpt-4o-transcribe`
- `gpt-4o-mini-transcribe`
- `whisper-1`

Supported translation models:

- `gpt-5.6-luna`
- `gpt-5.6-terra`
- `gpt-5.6-sol`

Common target tags offered by the GUI are `zh-TW`, `zh-CN`, `en`, `ja`, `ko`, `es`, `fr`, `de`, `it`, and `pt-BR`. The field remains editable, so other valid BCP 47 tags are accepted.

For `gpt-transcribe`, VoiceScribe sends `prompt`, `keywords`, and `languages`. Other transcription models receive a single `language` value and prompt text according to their supported interface.

## Development

Check Python syntax:

```bash
python -m py_compile app.py gui_app.py
```

Run the tests:

```bash
pytest -q
```

Tests use mocked OpenAI responses and do not make paid API calls.

## Version history

### v2.4.3

- Added transcript-only mode to both the CLI and GUI.
- Made the primary README and CLI help English for a broader audience.
- Added a complete Traditional Chinese companion README.
- Added cache-safety tests for switching between transcript-only and translated output.

### v2.4.2

- Added configurable target languages to the CLI and GUI while preserving `zh-TW` as the default.
- Included the target language in prompts, cache hashes, segment filenames, and manifests.
- Rewrote protected model instructions in English for multilingual maintenance.

### v2.4.1

- Treated blank ASR responses as silent chunks while still rejecting an entirely silent recording.

### v2.4.0

- Added direct file and directory CLI inputs, resumable processing, atomic output, structured translation validation, and low-memory FFmpeg segmentation.

## License

VoiceScribe is available under the [MIT License](LICENSE).
