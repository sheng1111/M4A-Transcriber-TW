"""Application configuration and stable defaults."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Tuple


APP_VERSION = "2.4.3"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-transcribe"
DEFAULT_TRANSLATION_MODEL = "gpt-5.6-luna"
DEFAULT_TARGET_LANGUAGE = "zh-TW"
COMMON_TARGET_LANGUAGES = (
    "zh-TW",
    "zh-CN",
    "en",
    "ja",
    "ko",
    "es",
    "fr",
    "de",
    "it",
    "pt-BR",
)
SUPPORTED_TRANSCRIPTION_MODELS = (
    "gpt-transcribe",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "whisper-1",
)
SUPPORTED_TRANSLATION_MODELS = (
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
)
SUPPORTED_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".flac", ".aac", ".mp4", ".mpeg", ".webm"}


def _clean_items(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


@dataclass(frozen=True)
class AudioConfig:
    """FFmpeg conversion and segmentation settings."""

    max_size_mb: int = 20
    max_duration_min: int = 10
    bitrate_kbps: int = 96
    high_pass_freq: int = 80
    low_pass_freq: int = 8000
    target_dbfs: float = -20.0
    compression_ratio: float = 3.0
    voice_boost: bool = True

    def validate(self) -> None:
        if not 5 <= self.max_size_mb <= 24:
            raise ValueError("片段大小必須介於 5MB 和 24MB")
        if not 1 <= self.max_duration_min <= 30:
            raise ValueError("片段長度必須介於 1 和 30 分鐘")
        if self.bitrate_kbps < 32:
            raise ValueError("音訊位元率不可低於 32kbps")
        if self.high_pass_freq < 0 or self.low_pass_freq <= self.high_pass_freq:
            raise ValueError("高通與低通頻率設定無效")
        if self.compression_ratio < 1:
            raise ValueError("壓縮比例不可小於 1")


@dataclass(frozen=True)
class ProcessingConfig:
    """Complete, serializable processing configuration."""

    transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL
    translation_model: str = DEFAULT_TRANSLATION_MODEL
    target_language: str = DEFAULT_TARGET_LANGUAGE
    languages: Tuple[str, ...] = field(default_factory=tuple)
    keywords: Tuple[str, ...] = field(default_factory=tuple)
    recording_context: str = ""
    style_preference: str = ""
    transcript_only: bool = False
    asr_workers: int = 3
    translation_workers: int = 2
    retry_attempts: int = 3
    resume: bool = True
    audio: AudioConfig = field(default_factory=AudioConfig)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_language", self.target_language.strip())
        object.__setattr__(self, "languages", _clean_items(self.languages))
        object.__setattr__(self, "keywords", _clean_items(self.keywords))

    def validate(self) -> None:
        if self.transcription_model not in SUPPORTED_TRANSCRIPTION_MODELS:
            raise ValueError(f"不支援的轉錄模型: {self.transcription_model}")
        if self.translation_model not in SUPPORTED_TRANSLATION_MODELS:
            raise ValueError(f"不支援的翻譯模型: {self.translation_model}")
        if not self.target_language:
            raise ValueError("目標語言不可空白")
        if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", self.target_language):
            raise ValueError(f"目標語言代碼格式無效: {self.target_language}")
        if not 1 <= self.asr_workers <= 8 or not 1 <= self.translation_workers <= 8:
            raise ValueError("並行數必須介於 1 和 8")
        if not 1 <= self.retry_attempts <= 6:
            raise ValueError("重試次數必須介於 1 和 6")
        for keyword in self.keywords:
            if any(char in keyword for char in ("<", ">", "\r", "\n")):
                raise ValueError(f"關鍵字含有不允許的字元: {keyword!r}")
        self.audio.validate()

    def stage_hash(self, stage: str, raw_sha256: str = "") -> str:
        """Return a stable hash for cache invalidation."""
        if stage == "asr":
            payload = {
                "model": self.transcription_model,
                "languages": self.languages,
                "keywords": self.keywords,
                "context": self.recording_context,
                "audio": asdict(self.audio),
            }
        elif stage == "translation":
            payload = {
                "model": self.translation_model,
                "target_language": self.target_language,
                "keywords": self.keywords,
                "context": self.recording_context,
                "style": self.style_preference,
                "transcript_only": self.transcript_only,
                "reasoning_effort": "none",
                "verbosity": "high",
                "raw_sha256": raw_sha256,
            }
        else:
            raise ValueError(f"未知處理階段: {stage}")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
