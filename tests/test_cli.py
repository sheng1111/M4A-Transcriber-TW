import pytest

from app import build_parser, discover_inputs


def test_cli_accepts_files_and_recursively_discovers_directories(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    first = tmp_path / "a.m4a"
    second = nested / "b.wav"
    ignored = nested / "notes.txt"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    ignored.write_text("ignore", encoding="utf-8")
    assert discover_inputs([str(tmp_path)]) == [first.resolve(), second.resolve()]


def test_cli_reports_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError, match="找不到輸入路徑"):
        discover_inputs([str(tmp_path / "missing.m4a")])


def test_help_and_defaults_do_not_require_api_key():
    args = build_parser().parse_args(["sample.m4a"])
    assert args.transcription_model == "gpt-transcribe"
    assert args.translation_model == "gpt-5.6-luna"
    assert args.target_language == "zh-TW"


def test_cli_accepts_a_custom_target_language():
    args = build_parser().parse_args(["sample.m4a", "--target-language", "ja"])
    assert args.target_language == "ja"


def test_cli_accepts_transcript_only_mode():
    args = build_parser().parse_args(["sample.m4a", "--transcript-only"])
    assert args.transcript_only is True
