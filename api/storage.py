"""Filesystem primitives for Dreamserver entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


TRANSCRIPT_FILENAMES = (
    "transcript_user.txt",
    "transcript_corrected.txt",
    "transcript_raw.txt",
)


def entry_path(entries_dir: Path, timestamp: str) -> Path:
    return Path(entries_dir) / timestamp


def iter_entry_paths(entries_dir: Path) -> Iterable[Path]:
    if not entries_dir.exists():
        return
    yield from sorted(
        (entry for entry in entries_dir.iterdir() if entry.is_dir()),
        reverse=True,
    )


def read_meta(entry_dir: Path) -> dict | None:
    meta_path = Path(entry_dir) / "meta.json"
    if not meta_path.exists():
        return None
    with open(meta_path) as meta_file:
        return json.load(meta_file)


def write_meta(entry_dir: Path, meta: dict) -> None:
    with open(Path(entry_dir) / "meta.json", "w") as meta_file:
        json.dump(meta, meta_file, indent=2)


def update_meta(entry_dir: Path, updates: dict) -> dict:
    meta = read_meta(entry_dir) or {}
    meta.update(updates)
    write_meta(entry_dir, meta)
    return meta


def read_preferred_transcript(entry_dir: Path) -> str:
    for filename in TRANSCRIPT_FILENAMES:
        transcript_path = Path(entry_dir) / filename
        if transcript_path.exists():
            return transcript_path.read_text()
    return ""


def read_transcripts(entry_dir: Path) -> dict:
    transcripts = {}
    for filename in reversed(TRANSCRIPT_FILENAMES):
        transcript_path = Path(entry_dir) / filename
        if transcript_path.exists():
            key = filename.removeprefix("transcript_").removesuffix(".txt")
            transcripts[f"transcript_{key}"] = transcript_path.read_text()
    return transcripts


def write_transcript(entry_dir: Path, kind: str, text: str) -> None:
    if kind not in {"raw", "corrected", "user"}:
        raise ValueError(f"Unsupported transcript kind: {kind}")
    (Path(entry_dir) / f"transcript_{kind}.txt").write_text(text)


def find_audio(entry_dir: Path) -> Path | None:
    return next(Path(entry_dir).glob("audio.*"), None)