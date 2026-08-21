from dataclasses import replace

import pytest

from transcriber.config import AudioConfig, ProcessingConfig
from transcriber.prompts import batch_segments, normalize_output, split_transcript


def test_config_hashes_invalidate_only_relevant_stage():
    base = ProcessingConfig(keywords=("OpenAI",), languages=("zh", "en"))
    style_changed = replace(base, style_preference="每段空一行")
    assert base.stage_hash("asr") == style_changed.stage_hash("asr")
    assert base.stage_hash("translation", "raw") != style_changed.stage_hash("translation", "raw")


def test_config_rejects_invalid_keyword_and_audio_limit():
    with pytest.raises(ValueError, match="關鍵字"):
        ProcessingConfig(keywords=("bad\nterm",)).validate()
    with pytest.raises(ValueError, match="片段大小"):
        ProcessingConfig(audio=AudioConfig(max_size_mb=25)).validate()


def test_split_transcript_preserves_all_text_and_stable_ids():
    source = "第一句。 第二句。\n第三句。"
    segments = split_transcript(source, max_chars=8)
    assert [segment["id"] for segment in segments] == [f"s{index:05d}" for index in range(1, len(segments) + 1)]
    compact_source = "".join(source.split())
    compact_segments = "".join(segment["text"].replace(" ", "") for segment in segments)
    assert compact_segments == compact_source


def test_batching_and_normalization_are_deterministic():
    segments = [{"id": f"s{i}", "text": "內容" * 3} for i in range(5)]
    batches = batch_segments(segments, max_chars=12, max_items=2)
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert normalize_output("第一段  \n\n\n第一段\n第二段") == "第一段\n第二段"
