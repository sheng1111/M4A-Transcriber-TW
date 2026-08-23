"""Command-line entry point for VoiceScribe."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv

from transcriber import AudioProcessor
from transcriber.config import (
    APP_VERSION,
    AudioConfig,
    DEFAULT_TARGET_LANGUAGE,
    DEFAULT_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSLATION_MODEL,
    ProcessingConfig,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_TRANSCRIPTION_MODELS,
    SUPPORTED_TRANSLATION_MODELS,
)
from transcriber.pipeline import ProcessingCancelled, TranscriptionPipeline


LOGGER = logging.getLogger("voicescribe")

__all__ = ["AudioProcessor", "build_parser", "discover_inputs", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe audio and optionally translate it (default target: zh-TW)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("inputs", nargs="*", help="Audio files or directories; scans speech/ by default")
    parser.add_argument("-o", "--output-dir", default=os.getenv("TEXT_DIR", "./text"), help="Output root directory")
    parser.add_argument("--context", default="", help="Recording context; must not contain translation instructions")
    parser.add_argument("--keyword", action="append", default=[], help="Expected proper noun; may be repeated")
    parser.add_argument("--language", action="append", default=[], help="Expected audio language code; may be repeated")
    parser.add_argument(
        "--target-language",
        default=DEFAULT_TARGET_LANGUAGE,
        help="BCP 47 target language tag, for example zh-TW, en, or ja",
    )
    parser.add_argument(
        "--transcription-model",
        choices=SUPPORTED_TRANSCRIPTION_MODELS,
        default=DEFAULT_TRANSCRIPTION_MODEL,
    )
    parser.add_argument(
        "--translation-model",
        choices=SUPPORTED_TRANSLATION_MODELS,
        default=DEFAULT_TRANSLATION_MODEL,
    )
    parser.add_argument("--style", default="", help="Formatting preference; cannot override fidelity rules")
    parser.add_argument("--transcript-only", action="store_true", help="Skip translation and write the transcript to final.txt")
    parser.add_argument("--max-size-mb", type=int, default=20, help="Maximum upload chunk size")
    parser.add_argument("--max-duration-min", type=int, default=10, help="Maximum audio chunk duration")
    parser.add_argument("--asr-workers", type=int, default=3, help="Concurrent transcription workers")
    parser.add_argument("--translation-workers", type=int, default=2, help="Concurrent translation workers")
    parser.add_argument("--no-resume", action="store_true", help="Ignore reusable results with matching settings")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    return parser


def discover_inputs(values: Iterable[str], default_dir: Path = Path("./speech")) -> List[Path]:
    requested = [Path(value).expanduser() for value in values]
    if not requested:
        requested = [default_dir]
    discovered: List[Path] = []
    missing: List[Path] = []
    for value in requested:
        if value.is_file():
            if value.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                discovered.append(value.resolve())
        elif value.is_dir():
            discovered.extend(
                path.resolve()
                for path in sorted(value.rglob("*"))
                if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            )
        else:
            missing.append(value)
    if missing:
        raise FileNotFoundError("找不到輸入路徑: " + ", ".join(str(path) for path in missing))
    return list(dict.fromkeys(discovered))


def _progress(event) -> None:
    stage = event["stage"]
    if stage in ("transcribing", "translating"):
        LOGGER.info("%s: %s/%s", stage, event.get("completed", 0), event.get("total", 0))
    elif stage in ("completed", "completed_cached"):
        LOGGER.info("處理完成: %s", event.get("path", ""))
    elif stage.endswith("cached"):
        LOGGER.info("使用可續跑結果: %s", event.get("source", ""))
    else:
        LOGGER.info("處理階段: %s", stage)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    try:
        inputs = discover_inputs(args.inputs)
        if not inputs:
            parser.error("找不到支援的音檔")
        load_dotenv(".env")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            parser.error("OPENAI_API_KEY 未設定，請建立 .env 或設定環境變數")
        config = ProcessingConfig(
            transcription_model=args.transcription_model,
            translation_model=args.translation_model,
            target_language=args.target_language,
            languages=tuple(args.language),
            keywords=tuple(args.keyword),
            recording_context=args.context,
            style_preference=args.style,
            transcript_only=args.transcript_only,
            asr_workers=args.asr_workers,
            translation_workers=args.translation_workers,
            resume=not args.no_resume,
            audio=AudioConfig(
                max_size_mb=args.max_size_mb,
                max_duration_min=args.max_duration_min,
            ),
        )
        config.validate()
        pipeline = TranscriptionPipeline(api_key=api_key)
        failures = []
        for source in inputs:
            LOGGER.info("開始處理: %s", source)
            try:
                pipeline.process(source, args.output_dir, config, progress=_progress)
            except Exception as exc:
                failures.append((source, exc))
                LOGGER.error("處理失敗: %s: %s", source.name, exc)
        if failures:
            LOGGER.error("完成時有 %d/%d 個檔案失敗", len(failures), len(inputs))
            return 1
        return 0
    except ProcessingCancelled:
        LOGGER.warning("處理已取消")
        return 130
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    sys.exit(main())
