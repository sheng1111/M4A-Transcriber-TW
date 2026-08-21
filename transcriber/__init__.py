"""VoiceScribe core package."""

from .config import APP_VERSION, ProcessingConfig
from .pipeline import AudioProcessor, ProcessingResult, TranscriptionPipeline

__all__ = [
    "APP_VERSION",
    "AudioProcessor",
    "ProcessingConfig",
    "ProcessingResult",
    "TranscriptionPipeline",
]
