# Developer Guide

## Project

M4A Transcriber TW v2.4.0 converts recorded audio into a raw transcript and a faithful Taiwan Traditional Chinese result. `app.py` and `gui_app.py` are entry points; reusable code lives in `transcriber/`.

## Architecture

- `config.py`: immutable settings, model registries and cache hashes.
- `audio.py`: ffprobe inspection and low-memory FFmpeg segmentation.
- `openai_service.py`: OpenAI transcription, Responses API translation, retries and output validation.
- `prompts.py`: protected fidelity rules and deterministic text segmentation.
- `storage.py`: source hashing, job paths, manifests and atomic writes.
- `pipeline.py`: resumable orchestration and compatibility `AudioProcessor` wrapper.

Results use `text/<source>/raw.txt`, `final.txt`, `manifest.json` and `chunks/`. A final file is written only after all source segment IDs have valid translated output.

## Commands

```bash
python app.py --help
python gui_app.py
python -m py_compile app.py gui_app.py
pytest -q
```

## Rules

- Do not modify `requirements.txt`.
- Do not place input paths, personal keywords or API keys in Python files.
- Keep the protected translation prompt authoritative over user style additions.
- Keep Tk calls on the main thread; background work communicates through the GUI event queue.
- Preserve atomic final writes, per-stage cache invalidation and temporary audio cleanup.
- Tests must mock OpenAI calls and must not spend API credits.
