from datetime import datetime

from api.analytics import compute_stats, compute_weekly_digest, search_entries, stats_tokens
from api.storage import write_meta, write_transcript


def test_search_returns_excerpt_and_match_position(tmp_path):
    entries_dir = tmp_path / "entries"
    entry_dir = entries_dir / "2026-01-01_07h00"
    entry_dir.mkdir(parents=True)
    write_meta(entry_dir, {"timestamp": entry_dir.name})
    write_transcript(entry_dir, "raw", "Avant une grande maison pres de la mer ensuite.")

    results = search_entries(entries_dir, "maison")

    assert len(results) == 1
    assert results[0]["timestamp"] == entry_dir.name
    assert results[0]["search_match_pos"] == 17
    assert "maison" in results[0]["search_excerpt"]


def test_search_prefers_user_transcript_and_normalizes_metadata(tmp_path):
    entries_dir = tmp_path / "entries"
    entry_dir = entries_dir / "2026-01-02_07h00"
    entry_dir.mkdir(parents=True)
    write_meta(entry_dir, {"timestamp": entry_dir.name})
    write_transcript(entry_dir, "raw", "raw text")
    write_transcript(entry_dir, "user", "Edited dream about a lighthouse")

    def normalize(meta):
        meta["normalized"] = True
        return meta

    results = search_entries(entries_dir, "lighthouse", normalize)

    assert results[0]["normalized"] is True
    assert "lighthouse" in results[0]["search_excerpt"]


def test_search_ignores_short_queries_and_missing_entries(tmp_path):
    entries_dir = tmp_path / "entries"

    assert search_entries(entries_dir, "a") == []
    assert search_entries(entries_dir, "missing") == []


def test_stats_tokens_filters_stopwords_and_normalizes_elisions():
    tokens = stats_tokens("J'avais une maison, avec l'eau et des rêves lumineux.")

    assert "avais" in tokens
    assert "une" not in tokens
    assert "avec" not in tokens
    assert "maison" in tokens
    assert "eau" not in tokens
    assert "rêves" in tokens
    assert "lumineux" in tokens


def test_compute_stats_aggregates_entries_and_recent_tags(tmp_path):
    entries_dir = tmp_path / "entries"
    recent = entries_dir / "2026-09-20_07h00"
    old = entries_dir / "2026-07-01_07h00"
    recent.mkdir(parents=True)
    old.mkdir(parents=True)
    write_meta(
        recent,
        {
            "timestamp": recent.name,
            "transcribed": True,
            "tags": ["water", "shared"],
        },
    )
    write_meta(
        old,
        {"timestamp": old.name, "transcribed": True, "tags": ["shared"]},
    )
    write_transcript(recent, "raw", "A blue house near water")
    write_transcript(old, "raw", "A quiet house")

    stats = compute_stats(entries_dir, now=datetime(2026, 9, 23))

    assert stats["total_entries"] == 2
    assert stats["avg_length"] == 18
    assert stats["avg_per_month"] == 1.0
    assert stats["top_tags"] == [("shared", 2), ("water", 1)]
    assert stats["top_tags_30"] == [("water", 1), ("shared", 1)]
    assert stats["top_words"][0] == ("house", 2)
    assert stats["monthly"] == [("2026-07", 1), ("2026-09", 1)]


def test_compute_stats_returns_empty_payload_without_entries(tmp_path):
    assert compute_stats(tmp_path / "missing") == {}


def test_compute_weekly_digest_builds_window_highlights_and_tension(tmp_path):
    entries_dir = tmp_path / "entries"
    entry_dir = entries_dir / "2026-09-17_07h00"
    entry_dir.mkdir(parents=True)
    write_meta(
        entry_dir,
        {
            "timestamp": entry_dir.name,
            "dream_date": "2026-09-17T07:00:00",
            "transcribed": True,
            "tags": ["cauchemar", "eau"],
        },
    )
    write_transcript(entry_dir, "raw", "Une poursuite dans l'eau")

    digest = compute_weekly_digest(
        entries_dir, weeks_ago=1, now=datetime(2026, 9, 23)
    )

    assert digest["window_start"] == "2026-09-14"
    assert digest["window_end"] == "2026-09-20"
    assert digest["week_complete"] is True
    assert digest["total_entries"] == 1
    assert digest["nightmare_entries"] == 1
    assert digest["tension_level"] == "high"
    assert digest["top_tags"] == [("cauchemar", 1), ("eau", 1)]
    assert digest["highlights"][0]["timestamp"] == entry_dir.name


def test_compute_weekly_digest_returns_empty_week(tmp_path):
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    digest = compute_weekly_digest(entries_dir, now=datetime(2026, 9, 23))

    assert digest["total_entries"] == 0
    assert digest["nightmare_entries"] == 0
    assert len(digest["daily"]) == 7