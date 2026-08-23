"""Atomic artifact storage and resumable job manifests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .config import APP_VERSION, DEFAULT_TARGET_LANGUAGE


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_stem(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(" .")
    return cleaned or "untitled"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, content: str) -> None:
    _atomic_write(path, content)


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


@dataclass
class JobStore:
    root: Path
    source: Path
    source_hash: str

    @classmethod
    def create(cls, output_root: Path, source: Path, source_hash: str) -> "JobStore":
        base = output_root / safe_stem(source.stem)
        root = base
        manifest_path = base / "manifest.json"
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            if existing.get("source", {}).get("sha256") not in (None, source_hash):
                root = output_root / f"{safe_stem(source.stem)}--{source_hash[:8]}"
        elif base.exists() and any(base.iterdir()):
            root = output_root / f"{safe_stem(source.stem)}--{source_hash[:8]}"
        return cls(root=root, source=source, source_hash=source_hash)

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def raw_path(self) -> Path:
        return self.root / "raw.txt"

    @property
    def final_path(self) -> Path:
        return self.root / "final.txt"

    @property
    def chunks_dir(self) -> Path:
        return self.root / "chunks"

    def raw_chunk_path(self, index: int) -> Path:
        return self.chunks_dir / f"a{index:04d}.raw.txt"

    def translated_segment_path(
        self, segment_id: str, target_language: str = DEFAULT_TARGET_LANGUAGE
    ) -> Path:
        # Language tags are validated by ProcessingConfig; safe_stem adds defense in depth.
        return self.chunks_dir / f"{segment_id}.{safe_stem(target_language)}.txt"

    def load_manifest(self) -> Dict[str, Any]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def new_manifest(self) -> Dict[str, Any]:
        stat = self.source.stat()
        return {
            "schema_version": 1,
            "app_version": APP_VERSION,
            "status": "pending",
            "source": {
                "path": str(self.source.resolve()),
                "name": self.source.name,
                "sha256": self.source_hash,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            },
            "cache": {},
            "audio_chunks": [],
            "translation_segments": {},
            "artifacts": {},
            "error": None,
        }

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.manifest_path, manifest)

    def cached_text(self, path: Path) -> Optional[str]:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None
