"""Low-memory FFmpeg audio preparation."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import AudioConfig


LOGGER = logging.getLogger(__name__)


class AudioProcessingError(RuntimeError):
    pass


@dataclass
class AudioChunks:
    directory: Path
    files: List[Path]

    def cleanup(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def __enter__(self) -> "AudioChunks":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.cleanup()


class FFmpegAudioChunker:
    """Segment recordings through FFmpeg without loading them into Python memory."""

    def __init__(self, ffmpeg: str = "", ffprobe: str = "") -> None:
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or ""
        self.ffprobe = ffprobe or shutil.which("ffprobe") or ""
        if not self.ffmpeg or not self.ffprobe:
            raise AudioProcessingError("找不到 FFmpeg 或 FFprobe，請先安裝並加入 PATH")

    def probe_duration(self, source: Path) -> float:
        command = [
            self.ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            duration = float(json.loads(result.stdout)["format"]["duration"])
        except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise AudioProcessingError(f"無法讀取音檔資訊: {detail.strip()}") from exc
        if duration <= 0:
            raise AudioProcessingError("音檔長度為 0")
        return duration

    def _filters(self, config: AudioConfig) -> str:
        filters = []
        if config.high_pass_freq:
            filters.append(f"highpass=f={config.high_pass_freq}")
        if config.low_pass_freq:
            filters.append(f"lowpass=f={config.low_pass_freq}")
        if config.voice_boost:
            filters.append("equalizer=f=1700:t=q:w=1:g=2")
        if config.compression_ratio > 1:
            filters.append(
                f"acompressor=ratio={config.compression_ratio:.2f}:threshold=-18dB:attack=20:release=250"
            )
        filters.append(f"loudnorm=I={config.target_dbfs:.1f}:TP=-2:LRA=11")
        return ",".join(filters)

    def _segment(self, source: Path, pattern: Path, seconds: int, config: AudioConfig) -> None:
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            f"{config.bitrate_kbps}k",
            "-af",
            self._filters(config),
            "-f",
            "segment",
            "-segment_time",
            str(seconds),
            "-reset_timestamps",
            "1",
            str(pattern),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise AudioProcessingError(f"FFmpeg 音檔切割失敗: {(exc.stderr or str(exc)).strip()}") from exc

    def split(self, source: Path, config: AudioConfig) -> AudioChunks:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise AudioProcessingError(f"找不到音檔: {source}")
        config.validate()
        duration = self.probe_duration(source)
        max_bytes = config.max_size_mb * 1024 * 1024
        size_seconds = int((max_bytes * 8 * 0.88) / (config.bitrate_kbps * 1000))
        segment_seconds = max(30, min(config.max_duration_min * 60, size_seconds))
        directory = Path(tempfile.mkdtemp(prefix="voicescribe_"))
        try:
            self._segment(source, directory / "chunk_%04d.mp3", segment_seconds, config)
            files = sorted(directory.glob("chunk_*.mp3"))
            if not files:
                raise AudioProcessingError("FFmpeg 未產生任何音訊片段")

            verified: List[Path] = []
            for index, chunk in enumerate(files):
                if chunk.stat().st_size <= max_bytes:
                    verified.append(chunk)
                    continue
                LOGGER.warning("片段 %s 超過大小限制，將再次切割", index + 1)
                sub_pattern = directory / f"resplit_{index:04d}_%04d.mp3"
                self._segment(chunk, sub_pattern, max(15, segment_seconds // 2), config)
                sub_chunks = sorted(directory.glob(f"resplit_{index:04d}_*.mp3"))
                if not sub_chunks or any(path.stat().st_size > max_bytes for path in sub_chunks):
                    raise AudioProcessingError(f"片段 {index + 1} 無法壓縮至 {config.max_size_mb}MB 以下")
                chunk.unlink(missing_ok=True)
                verified.extend(sub_chunks)

            LOGGER.info(
                "音檔長度 %.1f 分鐘，產生 %d 個片段，每段上限 %d 秒",
                duration / 60,
                len(verified),
                segment_seconds,
            )
            return AudioChunks(directory=directory, files=verified)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
