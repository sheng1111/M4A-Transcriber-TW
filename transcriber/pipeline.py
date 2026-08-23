"""Resumable transcription and faithful translation pipeline."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from dotenv import load_dotenv

from .audio import FFmpegAudioChunker
from .config import APP_VERSION, AudioConfig, ProcessingConfig
from .openai_service import OpenAIService
from .prompts import batch_segments, normalize_output, split_transcript
from .storage import JobStore, atomic_write_text, sha256_file, sha256_text


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[Dict[str, Any]], None]
StopCallback = Callable[[], bool]


class ProcessingCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessingResult:
    source: Path
    job_dir: Path
    raw_path: Path
    final_path: Path
    manifest_path: Path
    status: str
    resumed: bool = False


class TranscriptionPipeline:
    def __init__(
        self,
        api_key: str = "",
        service: Optional[OpenAIService] = None,
        chunker: Optional[FFmpegAudioChunker] = None,
    ) -> None:
        self.service = service or OpenAIService(api_key=api_key)
        self.chunker = chunker or FFmpegAudioChunker()

    @staticmethod
    def _emit(callback: Optional[ProgressCallback], stage: str, **details: Any) -> None:
        if callback:
            callback({"stage": stage, **details})

    @staticmethod
    def _check_stop(should_stop: Optional[StopCallback]) -> None:
        if should_stop and should_stop():
            raise ProcessingCancelled("使用者取消處理")

    def process(
        self,
        source: Path | str,
        output_root: Path | str,
        config: ProcessingConfig,
        progress: Optional[ProgressCallback] = None,
        should_stop: Optional[StopCallback] = None,
    ) -> ProcessingResult:
        source_path = Path(source).expanduser().resolve()
        output_path = Path(output_root).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"找不到音檔: {source_path}")
        config.validate()
        output_path.mkdir(parents=True, exist_ok=True)
        self.service.retry_attempts = config.retry_attempts

        self._emit(progress, "hashing", source=source_path.name)
        source_hash = sha256_file(source_path)
        store = JobStore.create(output_path, source_path, source_hash)
        previous = store.load_manifest()
        if previous.get("source", {}).get("sha256") == source_hash:
            manifest = previous
        else:
            manifest = store.new_manifest()
        manifest["app_version"] = APP_VERSION
        manifest["status"] = "running"
        manifest["error"] = None
        manifest.setdefault("cache", {})
        manifest.setdefault("audio_chunks", [])
        manifest.setdefault("translation_segments", {})
        store.save_manifest(manifest)

        resumed = False
        try:
            self._check_stop(should_stop)
            asr_hash = config.stage_hash("asr")
            raw_text = None
            if config.resume and manifest["cache"].get("asr") == asr_hash:
                raw_text = store.cached_text(store.raw_path)
                resumed = raw_text is not None
            if raw_text is None:
                raw_text = self._transcribe(
                    source_path, store, manifest, config, asr_hash, progress, should_stop
                )
            else:
                self._emit(progress, "asr_cached", source=source_path.name)

            self._check_stop(should_stop)
            raw_hash = sha256_text(raw_text)
            translation_hash = config.stage_hash("translation", raw_hash)
            if (
                config.resume
                and manifest["cache"].get("translation") == translation_hash
                and store.cached_text(store.final_path)
            ):
                manifest["status"] = "completed"
                manifest["error"] = None
                store.save_manifest(manifest)
                self._emit(progress, "completed_cached", source=source_path.name, path=str(store.final_path))
                return ProcessingResult(
                    source_path,
                    store.root,
                    store.raw_path,
                    store.final_path,
                    store.manifest_path,
                    "completed",
                    True,
                )

            final_text = self._translate(
                raw_text, store, manifest, config, translation_hash, progress, should_stop
            )
            if not final_text:
                raise RuntimeError("翻譯結果為空，未覆寫既有成品")
            atomic_write_text(store.final_path, final_text.rstrip() + "\n")
            manifest["cache"]["translation"] = translation_hash
            manifest["status"] = "completed"
            manifest["error"] = None
            manifest["artifacts"] = {"raw": "raw.txt", "final": "final.txt"}
            store.save_manifest(manifest)
            self._emit(progress, "completed", source=source_path.name, path=str(store.final_path))
            return ProcessingResult(
                source_path,
                store.root,
                store.raw_path,
                store.final_path,
                store.manifest_path,
                "completed",
                resumed,
            )
        except ProcessingCancelled as exc:
            manifest["status"] = "cancelled"
            manifest["error"] = str(exc)
            store.save_manifest(manifest)
            self._emit(progress, "cancelled", source=source_path.name)
            raise
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            store.save_manifest(manifest)
            self._emit(progress, "failed", source=source_path.name, error=str(exc))
            raise

    def _transcribe(
        self,
        source: Path,
        store: JobStore,
        manifest: Dict[str, Any],
        config: ProcessingConfig,
        asr_hash: str,
        progress: Optional[ProgressCallback],
        should_stop: Optional[StopCallback],
    ) -> str:
        self._emit(progress, "splitting", source=source.name)
        manifest["cache"]["asr_in_progress"] = asr_hash
        store.save_manifest(manifest)
        with self.chunker.split(source, config.audio) as chunks:
            total = len(chunks.files)
            old_records = {item.get("index"): item for item in manifest.get("audio_chunks", [])}
            results: List[Optional[str]] = [None] * total
            records: List[Dict[str, Any]] = [
                {"index": index, "status": "pending", "path": store.raw_chunk_path(index).name}
                for index in range(total)
            ]

            def worker(index: int, audio_path: Path) -> str:
                self._check_stop(should_stop)
                cached_path = store.raw_chunk_path(index)
                cached_record = old_records.get(index, {})
                if (
                    config.resume
                    and manifest["cache"].get("asr_in_progress") == asr_hash
                    and cached_record.get("status") == "completed"
                ):
                    try:
                        return cached_path.read_text(encoding="utf-8").strip()
                    except OSError:
                        pass
                return self.service.transcribe(audio_path, config)

            errors: List[Exception] = []
            with ThreadPoolExecutor(max_workers=config.asr_workers) as executor:
                futures = {
                    executor.submit(worker, index, audio_path): index
                    for index, audio_path in enumerate(chunks.files)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        text = future.result()
                        results[index] = text
                        atomic_write_text(store.raw_chunk_path(index), text.rstrip() + "\n")
                        records[index]["status"] = "completed"
                        records[index]["characters"] = len(text)
                    except Exception as exc:
                        records[index]["status"] = "failed"
                        records[index]["error"] = f"{type(exc).__name__}: {exc}"
                        errors.append(exc)
                    manifest["audio_chunks"] = records
                    store.save_manifest(manifest)
                    completed = sum(item["status"] == "completed" for item in records)
                    self._emit(progress, "transcribing", source=source.name, completed=completed, total=total)
            if errors:
                cancelled = next(
                    (error for error in errors if isinstance(error, ProcessingCancelled)),
                    None,
                )
                if cancelled is not None:
                    raise cancelled
                raise RuntimeError(f"{len(errors)} 個音訊片段轉錄失敗: {errors[0]}") from errors[0]
            if any(result is None for result in results):
                raise RuntimeError("轉錄片段不完整")
            raw_text = "\n\n".join(result.strip() for result in results if result).strip()
            if not raw_text:
                raise RuntimeError("所有音訊片段皆為空白")
            atomic_write_text(store.raw_path, raw_text + "\n")
            manifest["cache"]["asr"] = asr_hash
            manifest["cache"].pop("asr_in_progress", None)
            manifest["audio_chunks"] = records
            store.save_manifest(manifest)
            return raw_text

    def _translate(
        self,
        raw_text: str,
        store: JobStore,
        manifest: Dict[str, Any],
        config: ProcessingConfig,
        translation_hash: str,
        progress: Optional[ProgressCallback],
        should_stop: Optional[StopCallback],
    ) -> str:
        segments = split_transcript(raw_text)
        if not segments:
            raise RuntimeError("原始轉錄無法切成文字段落")
        prior_hash = manifest["cache"].get("translation_in_progress")
        prior_records = manifest.get("translation_segments", {}) if prior_hash == translation_hash else {}
        manifest["cache"]["translation_in_progress"] = translation_hash
        manifest["translation_segments"] = prior_records
        store.save_manifest(manifest)

        translated: Dict[str, str] = {}
        missing = []
        for segment in segments:
            segment_id = segment["id"]
            cached = None
            if config.resume and prior_records.get(segment_id, {}).get("status") == "completed":
                cached = store.cached_text(
                    store.translated_segment_path(segment_id, config.target_language)
                )
            if cached is None:
                missing.append(segment)
            else:
                translated[segment_id] = cached

        batches = batch_segments(missing)

        def worker(batch: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
            self._check_stop(should_stop)
            return self.service.translate_batch(batch, config)

        errors: List[Exception] = []
        completed_count = len(translated)
        with ThreadPoolExecutor(max_workers=config.translation_workers) as executor:
            futures = {executor.submit(worker, batch): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    for item in future.result():
                        segment_id = item["id"]
                        text = item["text"].strip()
                        translated[segment_id] = text
                        atomic_write_text(
                            store.translated_segment_path(segment_id, config.target_language),
                            text + ("\n" if text else ""),
                        )
                        prior_records[segment_id] = {"status": "completed", "characters": len(text)}
                        completed_count += 1
                except Exception as exc:
                    errors.append(exc)
                    for item in batch:
                        prior_records[item["id"]] = {
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                manifest["translation_segments"] = prior_records
                store.save_manifest(manifest)
                self._emit(
                    progress,
                    "translating",
                    source=store.source.name,
                    completed=completed_count,
                    total=len(segments),
                )
        if errors:
            cancelled = next(
                (error for error in errors if isinstance(error, ProcessingCancelled)),
                None,
            )
            if cancelled is not None:
                raise cancelled
            raise RuntimeError(f"{len(errors)} 批文字翻譯失敗: {errors[0]}") from errors[0]
        expected_ids = [segment["id"] for segment in segments]
        if any(segment_id not in translated for segment_id in expected_ids):
            raise RuntimeError("翻譯段落不完整")
        final_text = normalize_output("\n\n".join(translated[segment_id] for segment_id in expected_ids))
        manifest["translation_segments"] = prior_records
        manifest["target_language"] = config.target_language
        manifest["cache"].pop("translation_in_progress", None)
        store.save_manifest(manifest)
        return final_text


class AudioProcessor:
    """Compatibility wrapper around the reusable transcription pipeline."""

    def __init__(self, audio_dir: str = "./speech", text_dir: str = "./text", api_key: str = "") -> None:
        load_dotenv(".env")
        self.audio_dir = audio_dir
        self.text_dir = text_dir
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY 未設定")
        self.pipeline = TranscriptionPipeline(api_key=key)

    def process_files(
        self,
        file_paths,
        output_file=None,
        whisper_prompt="",
        gpt_system_prompt=None,
        transcription_model="gpt-transcribe",
        translation_model="gpt-5.6-luna",
        transcription_language="",
        target_language="zh-TW",
        should_stop=None,
        **audio_filter_params,
    ):
        output_root = Path(output_file).parent if output_file else Path(self.text_dir)
        languages = tuple(filter(None, [transcription_language]))
        keywords = tuple(part.strip() for part in whisper_prompt.split(",") if part.strip())
        audio = AudioConfig(
            max_size_mb=int(audio_filter_params.pop("max_size_mb", 20)),
            max_duration_min=int(audio_filter_params.pop("max_duration_min", 10)),
            high_pass_freq=int(audio_filter_params.pop("high_pass_freq", 80)),
            low_pass_freq=int(audio_filter_params.pop("low_pass_freq", 8000)),
            target_dbfs=float(audio_filter_params.pop("target_dBFS", -20.0)),
            compression_ratio=float(audio_filter_params.pop("compression_ratio", 3.0)),
            voice_boost=bool(audio_filter_params.pop("voice_boost", True)),
        )
        config = ProcessingConfig(
            transcription_model=transcription_model,
            translation_model=translation_model,
            target_language=target_language,
            languages=languages,
            keywords=keywords,
            style_preference=gpt_system_prompt or "",
            audio=audio,
        )
        return [
            self.pipeline.process(path, output_root, config, should_stop=should_stop)
            for path in file_paths
        ]
