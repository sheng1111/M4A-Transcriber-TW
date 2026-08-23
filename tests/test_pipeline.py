import json
from pathlib import Path

import pytest

from transcriber.config import ProcessingConfig
from transcriber.pipeline import ProcessingCancelled, TranscriptionPipeline


class FakeChunkSet:
    def __init__(self, files):
        self.files = files

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeChunker:
    def __init__(self, tmp_path):
        self.calls = 0
        self.files = [tmp_path / "chunk_0000.mp3", tmp_path / "chunk_0001.mp3"]
        for path in self.files:
            path.write_bytes(path.name.encode())

    def split(self, source, config):
        self.calls += 1
        return FakeChunkSet(self.files)


class FakeService:
    def __init__(self):
        self.retry_attempts = 0
        self.transcribe_calls = 0
        self.translate_calls = 0
        self.fail_translation = False

    def transcribe(self, audio_path, config):
        self.transcribe_calls += 1
        return f"raw {Path(audio_path).stem}."

    def translate_batch(self, segments, config):
        self.translate_calls += 1
        if self.fail_translation:
            raise RuntimeError("translation unavailable")
        return [{"id": segment["id"], "text": f"繁中 {segment['text']}"} for segment in segments]


def test_pipeline_writes_classified_artifacts_and_resumes(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    service = FakeService()
    chunker = FakeChunker(tmp_path)
    pipeline = TranscriptionPipeline(service=service, chunker=chunker)
    config = ProcessingConfig()

    first = pipeline.process(source, tmp_path / "text", config)
    assert first.status == "completed"
    assert first.raw_path.read_text(encoding="utf-8").startswith("raw chunk_0000")
    assert "繁中" in first.final_path.read_text(encoding="utf-8")
    assert first.manifest_path.exists()
    assert list((first.job_dir / "chunks").glob("*.raw.txt"))
    assert list((first.job_dir / "chunks").glob("*.zh-TW.txt"))
    calls = (service.transcribe_calls, service.translate_calls, chunker.calls)

    second = pipeline.process(source, tmp_path / "text", config)
    assert second.resumed is True
    assert (service.transcribe_calls, service.translate_calls, chunker.calls) == calls


def test_target_language_changes_translation_cache_and_segment_names(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    service = FakeService()
    pipeline = TranscriptionPipeline(service=service, chunker=FakeChunker(tmp_path))

    first = pipeline.process(source, tmp_path / "text", ProcessingConfig())
    pipeline.process(source, tmp_path / "text", ProcessingConfig(target_language="en"))

    assert service.transcribe_calls == 2
    assert service.translate_calls == 2
    assert list((first.job_dir / "chunks").glob("*.zh-TW.txt"))
    assert list((first.job_dir / "chunks").glob("*.en.txt"))
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["target_language"] == "en"


def test_transcript_only_skips_translation_and_writes_final(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    service = FakeService()
    pipeline = TranscriptionPipeline(service=service, chunker=FakeChunker(tmp_path))

    result = pipeline.process(
        source,
        tmp_path / "text",
        ProcessingConfig(transcript_only=True),
    )

    assert service.translate_calls == 0
    assert result.final_path.read_text(encoding="utf-8") == result.raw_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "transcript_only"
    assert manifest["target_language"] is None


def test_translation_after_transcript_only_does_not_reuse_raw_final(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    service = FakeService()
    pipeline = TranscriptionPipeline(service=service, chunker=FakeChunker(tmp_path))

    pipeline.process(source, tmp_path / "text", ProcessingConfig())
    pipeline.process(source, tmp_path / "text", ProcessingConfig(transcript_only=True))
    result = pipeline.process(source, tmp_path / "text", ProcessingConfig())

    assert service.translate_calls == 2
    assert "繁中" in result.final_path.read_text(encoding="utf-8")


def test_pipeline_ignores_a_silent_chunk_when_other_chunks_have_speech(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    service = FakeService()

    def transcribe(audio_path, config):
        service.transcribe_calls += 1
        return "" if Path(audio_path).stem == "chunk_0001" else "spoken content."

    service.transcribe = transcribe
    pipeline = TranscriptionPipeline(service=service, chunker=FakeChunker(tmp_path))

    result = pipeline.process(source, tmp_path / "text", ProcessingConfig())

    assert result.status == "completed"
    assert result.raw_path.read_text(encoding="utf-8") == "spoken content.\n"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [chunk["characters"] for chunk in manifest["audio_chunks"]] == [15, 0]


def test_pipeline_rejects_an_entirely_silent_recording(tmp_path):
    source = tmp_path / "silent.m4a"
    source.write_bytes(b"recording")
    service = FakeService()
    service.transcribe = lambda audio_path, config: ""
    pipeline = TranscriptionPipeline(service=service, chunker=FakeChunker(tmp_path))

    with pytest.raises(RuntimeError, match="所有音訊片段皆為空白"):
        pipeline.process(source, tmp_path / "text", ProcessingConfig())


def test_failed_new_translation_does_not_overwrite_previous_final(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    service = FakeService()
    pipeline = TranscriptionPipeline(service=service, chunker=FakeChunker(tmp_path))
    first = pipeline.process(source, tmp_path / "text", ProcessingConfig())
    original = first.final_path.read_text(encoding="utf-8")

    service.fail_translation = True
    changed = ProcessingConfig(style_preference="每段換行")
    with pytest.raises(RuntimeError, match="文字翻譯失敗"):
        pipeline.process(source, tmp_path / "text", changed)
    assert first.final_path.read_text(encoding="utf-8") == original


def test_cancellation_sets_manifest_without_final(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    pipeline = TranscriptionPipeline(service=FakeService(), chunker=FakeChunker(tmp_path))
    with pytest.raises(ProcessingCancelled):
        pipeline.process(source, tmp_path / "text", ProcessingConfig(), should_stop=lambda: True)
    assert not (tmp_path / "text" / "meeting" / "final.txt").exists()


def test_cancellation_inside_parallel_stage_remains_cancelled(tmp_path):
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"recording")
    pipeline = TranscriptionPipeline(service=FakeService(), chunker=FakeChunker(tmp_path))
    checks = 0

    def should_stop():
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(ProcessingCancelled):
        pipeline.process(source, tmp_path / "text", ProcessingConfig(), should_stop=should_stop)

    manifest = (tmp_path / "text" / "meeting" / "manifest.json").read_text(encoding="utf-8")
    assert '"status": "cancelled"' in manifest
