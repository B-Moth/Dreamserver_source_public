"""Analytics helpers that operate on the entry filesystem."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import calendar
from pathlib import Path
from typing import Callable

from api.storage import iter_entry_paths, read_meta, read_preferred_transcript


STATS_STOPWORDS = {
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "me", "te",
    "se", "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "y",
    "en", "et", "est", "était", "être", "avoir", "que", "qui", "quoi", "dont",
    "où", "ou", "mais", "donc", "or", "ni", "car", "si", "plus", "très", "bien",
    "tout", "tous", "cette", "ce", "cet", "ces", "mon", "ton", "son", "ma", "ta",
    "sa", "nos", "vos", "leurs", "leur", "au", "aux", "par", "pour", "sur", "sous",
    "dans", "avec", "sans", "entre", "vers", "chez", "après", "avant", "pendant",
    "alors", "puis", "aussi", "même", "comme", "quand", "encore", "déjà", "jamais",
    "toujours", "pas", "ne", "rien", "personne", "non", "oui", "ah", "oh", "a", "à",
    "ça", "là", "lui", "eux", "on", "j", "m", "t", "s", "c", "n", "qu", "j'ai",
    "j'étais", "c'est", "c'était", "avait", "était", "fait", "faire", "aller", "venir",
    "voir", "savoir", "pouvoir", "vouloir", "falloir", "dit", "allait", "venait", "ai",
    "as", "ont", "the", "and", "but", "with", "from", "this", "that", "they", "them",
    "their",
}

STATS_ELISION_PREFIXES = (
    "d'", "l'", "j'", "t'", "m'", "n'", "s'", "c'", "qu'", "puisqu'", "lorsqu'",
    "d’", "l’", "j’", "t’", "m’", "n’", "s’", "c’", "qu’", "puisqu’", "lorsqu’",
)


def stats_tokens(text: str) -> list[str]:
    import re

    tokens = re.findall(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ'’\-]{2,}", (text or "").lower())
    normalized = []
    for token in tokens:
        word = token.strip("-'’")
        for prefix in STATS_ELISION_PREFIXES:
            if word.startswith(prefix):
                word = word[len(prefix) :]
                break
        word = word.strip("-'’")
        if len(word) >= 4 and word not in STATS_STOPWORDS:
            normalized.append(word)
    return normalized


def compute_stats(entries_dir: Path, now: datetime | None = None) -> dict:
    """Compute the statistics payload returned by the stats endpoint."""
    if not entries_dir.exists():
        return {}

    entries = []
    all_words = []
    tag_counts = {}
    tag_counts_30 = {}
    total_chars = 0
    monthly = {}
    current_time = now or datetime.now()
    cutoff_30 = current_time - timedelta(days=30)

    for entry in iter_entry_paths(entries_dir):
        meta = read_meta(entry)
        if not meta or not meta.get("transcribed"):
            continue

        entries.append(meta)
        try:
            entry_date = datetime.strptime(
                meta.get("timestamp", "").split("_")[0], "%Y-%m-%d"
            )
            month_key = entry_date.strftime("%Y-%m")
            monthly[month_key] = monthly.get(month_key, 0) + 1
            is_recent = entry_date >= cutoff_30
        except Exception:
            is_recent = False

        text = read_preferred_transcript(entry).strip()
        total_chars += len(text)
        all_words.extend(stats_tokens(text))

        for tag in meta.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if is_recent:
                tag_counts_30[tag] = tag_counts_30.get(tag, 0) + 1

    total = len(entries)
    sorted_monthly = dict(sorted(monthly.items()))
    return {
        "total_entries": total,
        "avg_length": round(total_chars / total) if total > 0 else 0,
        "avg_per_month": round(total / max(len(sorted_monthly), 1), 1)
        if total > 0
        else 0,
        "top_tags": sorted(tag_counts.items(), key=lambda item: -item[1])[:15],
        "top_tags_30": sorted(tag_counts_30.items(), key=lambda item: -item[1])[:10],
        "top_words": Counter(all_words).most_common(30),
        "monthly": list(sorted_monthly.items())[-12:],
    }


DIGEST_STOPWORDS = {
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "me", "te", "se",
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "y", "en", "et",
    "est", "etait", "etre", "avoir", "que", "qui", "quoi", "dont", "ou", "mais", "donc",
    "or", "ni", "car", "si", "plus", "tres", "bien", "tout", "tous", "cette", "ce", "cet",
    "ces", "mon", "ton", "son", "ma", "ta", "sa", "nos", "vos", "leurs", "leur", "au",
    "aux", "par", "pour", "sur", "sous", "dans", "avec", "sans", "entre", "vers", "chez",
    "apres", "avant", "pendant", "alors", "puis", "aussi", "meme", "comme", "quand", "encore",
    "deja", "jamais", "toujours", "pas", "ne", "rien", "personne", "non", "oui", "suis", "etais",
    "étais", "etaient", "étaient", "avais", "avait", "avions", "aviez", "ont", "etre",
}

DIGEST_NIGHTMARE_TERMS = {
    "cauchemar", "peur", "angoisse", "panique", "sombre", "cri", "poursuite", "tomber"
}


def compute_weekly_digest(
    entries_dir: Path,
    days: int = 7,
    weeks_ago: int = 0,
    now: datetime | None = None,
) -> dict:
    """Compute the weekly digest payload returned by the API."""
    if not entries_dir.exists():
        return {"days": days, "entries": []}

    days = 7
    weeks_ago = max(0, min(int(weeks_ago or 0), 26))
    current_time = now or datetime.now()
    today = current_time.date()
    current_monday = today - timedelta(days=today.weekday())
    week_start_date = current_monday - timedelta(days=weeks_ago * 7)
    week_end_date = week_start_date + timedelta(days=6)
    week_complete = week_end_date < today

    def safe_parse_datetime(meta):
        for key in ("dream_date", "received_at"):
            raw = meta.get(key)
            if raw:
                try:
                    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if value.tzinfo is not None:
                        value = value.astimezone().replace(tzinfo=None)
                    return value
                except Exception:
                    pass
        try:
            return datetime.strptime(meta.get("timestamp", "").split("_")[0], "%Y-%m-%d")
        except Exception:
            return None

    entries = []
    tag_counter = Counter()
    word_counter = Counter()
    nightmare_count = 0
    daily_counter = Counter()

    month_ref = datetime.combine(week_end_date, datetime.min.time())
    month_start = datetime(month_ref.year, month_ref.month, 1)
    month_days = calendar.monthrange(month_ref.year, month_ref.month)[1]
    month_end = datetime(month_ref.year, month_ref.month, month_days, 23, 59, 59)
    month_night_counter = Counter()

    import re

    for entry in iter_entry_paths(entries_dir):
        meta = read_meta(entry)
        if not meta or not meta.get("transcribed"):
            continue
        dream_datetime = safe_parse_datetime(meta)
        if not dream_datetime:
            continue
        if not week_start_date <= dream_datetime.date() <= week_end_date:
            continue

        text = read_preferred_transcript(entry).strip()
        tags = [str(tag).strip().lower() for tag in (meta.get("tags") or []) if str(tag).strip()]
        tag_counter.update(tags)

        lowered = text.lower()
        tokens = re.findall(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ'’\-]{3,}", lowered)
        cleaned = []
        for token in tokens:
            word = token.strip("-'’")
            if word.startswith(("d'", "l'", "j'", "qu'", "d’", "l’", "j’", "qu’")):
                word = word.split("'", 1)[-1] if "'" in word else word.split("’", 1)[-1]
            word = word.strip("-'’")
            if len(word) >= 4 and word not in DIGEST_STOPWORDS:
                cleaned.append(word)
        word_counter.update(cleaned)

        is_nightmare = bool(DIGEST_NIGHTMARE_TERMS.intersection(set(tags))) or any(
            term in lowered for term in DIGEST_NIGHTMARE_TERMS
        )
        nightmare_count += int(is_nightmare)
        day_key = dream_datetime.strftime("%Y-%m-%d")
        daily_counter[day_key] += 1
        if month_start <= dream_datetime <= month_end:
            month_night_counter[dream_datetime.day] += 1

        entries.append(
            {
                "timestamp": meta.get("timestamp", entry.name),
                "dream_date": meta.get("dream_date") or meta.get("received_at"),
                "preview": (text[:170] + "…") if len(text) > 170 else text,
                "tags": tags[:6],
                "nightmare": is_nightmare,
            }
        )

    daily = [
        {
            "date": (week_start_date + timedelta(days=index)).strftime("%Y-%m-%d"),
            "count": daily_counter.get(
                (week_start_date + timedelta(days=index)).strftime("%Y-%m-%d"), 0
            ),
        }
        for index in range(7)
    ]
    total_entries = len(entries)
    ratio = nightmare_count / total_entries if total_entries else 0.0
    return {
        "days": 7,
        "weeks_ago": weeks_ago,
        "window_start": week_start_date.strftime("%Y-%m-%d"),
        "window_end": week_end_date.strftime("%Y-%m-%d"),
        "week_complete": week_complete,
        "calendar": {
            "year": month_ref.year,
            "month": month_ref.month,
            "first_weekday": month_start.weekday(),
            "days_in_month": month_days,
            "dream_nights": [
                {"day": day, "count": count}
                for day, count in sorted(month_night_counter.items())
            ],
        },
        "total_entries": total_entries,
        "nightmare_entries": nightmare_count,
        "nightmare_ratio": round(ratio, 2),
        "tension_level": "high" if ratio >= 0.45 else "medium" if ratio >= 0.2 else "low",
        "top_tags": tag_counter.most_common(10),
        "top_words": word_counter.most_common(12),
        "daily": daily,
        "highlights": entries[:8],
    }


def search_entries(
    entries_dir: Path,
    query: str,
    normalize_meta: Callable[[dict], dict] | None = None,
) -> list[dict]:
    """Search preferred transcripts and return API-ready entry metadata."""
    if not query or len(query.strip()) < 2:
        return []

    normalized_query = query.strip().lower()
    results = []
    for entry in iter_entry_paths(entries_dir):
        meta = read_meta(entry)
        if meta is None:
            continue

        transcript = read_preferred_transcript(entry)
        match_position = transcript.lower().find(normalized_query)
        if match_position < 0:
            continue

        if normalize_meta:
            meta = normalize_meta(meta)

        start = max(0, match_position - 60)
        end = min(len(transcript), match_position + len(normalized_query) + 60)
        meta["search_excerpt"] = (
            ("…" if start > 0 else "")
            + transcript[start:end]
            + ("…" if end < len(transcript) else "")
        )
        meta["search_match_pos"] = match_position
        results.append(meta)

    return results