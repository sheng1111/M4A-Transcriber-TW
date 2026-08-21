import json

from transcriber.storage import JobStore, atomic_write_text, sha256_file


def test_atomic_write_and_job_name_collision(tmp_path):
    source_a = tmp_path / "a" / "meeting.m4a"
    source_b = tmp_path / "b" / "meeting.m4a"
    source_a.parent.mkdir()
    source_b.parent.mkdir()
    source_a.write_bytes(b"first")
    source_b.write_bytes(b"second")
    output = tmp_path / "text"

    first_hash = sha256_file(source_a)
    first = JobStore.create(output, source_a, first_hash)
    manifest = first.new_manifest()
    first.save_manifest(manifest)
    atomic_write_text(first.final_path, "first result\n")
    assert first.final_path.read_text(encoding="utf-8") == "first result\n"

    second_hash = sha256_file(source_b)
    second = JobStore.create(output, source_b, second_hash)
    assert second.root.name == f"meeting--{second_hash[:8]}"
    assert json.loads(first.manifest_path.read_text(encoding="utf-8"))["source"]["sha256"] == first_hash
