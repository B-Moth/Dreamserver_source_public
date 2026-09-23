from api.storage import (
    entry_path,
    find_audio,
    iter_entry_paths,
    read_meta,
    read_preferred_transcript,
    read_transcripts,
    update_meta,
    write_meta,
    write_transcript,
)


def test_entry_paths_are_sorted_newest_first(tmp_path):
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    (entries_dir / "2026-01-01_07h00").mkdir()
    (entries_dir / "2026-02-01_07h00").mkdir()

    assert list(iter_entry_paths(entries_dir)) == [
        entries_dir / "2026-02-01_07h00",
        entries_dir / "2026-01-01_07h00",
    ]
    assert entry_path(entries_dir, "2026-02-01_07h00") == (
        entries_dir / "2026-02-01_07h00"
    )


def test_metadata_can_be_written_read_and_updated(tmp_path):
    entry_dir = tmp_path / "entry"
    entry_dir.mkdir()
    initial = {"timestamp": "2026-01-01_07h00", "transcribed": False}

    write_meta(entry_dir, initial)
    updated = update_meta(entry_dir, {"transcribed": True})

    assert read_meta(entry_dir) == {"timestamp": "2026-01-01_07h00", "transcribed": True}
    assert updated["transcribed"] is True


def test_preferred_transcript_uses_user_then_corrected_then_raw(tmp_path):
    entry_dir = tmp_path / "entry"
    entry_dir.mkdir()
    write_transcript(entry_dir, "raw", "raw text")
    assert read_preferred_transcript(entry_dir) == "raw text"

    write_transcript(entry_dir, "corrected", "corrected text")
    assert read_preferred_transcript(entry_dir) == "corrected text"

    write_transcript(entry_dir, "user", "user text")
    assert read_preferred_transcript(entry_dir) == "user text"


def test_read_transcripts_returns_available_named_files(tmp_path):
    entry_dir = tmp_path / "entry"
    entry_dir.mkdir()
    write_transcript(entry_dir, "raw", "raw text")
    write_transcript(entry_dir, "user", "user text")

    assert read_transcripts(entry_dir) == {
        "transcript_raw": "raw text",
        "transcript_user": "user text",
    }


def test_find_audio_returns_first_audio_file(tmp_path):
    entry_dir = tmp_path / "entry"
    entry_dir.mkdir()
    (entry_dir / "audio.webm").write_bytes(b"audio")

    assert find_audio(entry_dir) == entry_dir / "audio.webm"