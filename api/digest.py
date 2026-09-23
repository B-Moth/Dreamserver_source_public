"""Pure helpers for preparing weekly digest summaries and prompts."""

from __future__ import annotations

import json


def fallback_digest_summary(payload: dict) -> str:
    total = int(payload.get("total_entries") or 0)
    nightmares = int(payload.get("nightmare_entries") or 0)
    tension = payload.get("tension_level") or "low"
    top_tags = [tag for tag, _ in (payload.get("top_tags") or [])[:3]]
    top_words = [word for word, _ in (payload.get("top_words") or [])[:4]]

    if total == 0:
        return "Peu de donnees cette semaine: aucun reve transcrit sur la periode. Relance le digest apres de nouvelles entrees pour obtenir une synthese utile."

    return (
        f"Sur les {payload.get('days', 7)} derniers jours, {total} reves ont ete enregistres, dont {nightmares} a tonalite cauchemardesque. "
        f"Le niveau global de tension ressort comme {tension}. "
        f"Les themes qui reviennent le plus sont: {', '.join(top_tags) if top_tags else 'aucun tag dominant net'}. "
        f"Le vocabulaire recurrent met en avant: {', '.join(top_words) if top_words else 'peu de mots dominants'}. "
        "Piste utile: note au reveil un mot-emotion principal pour comparer son evolution sur les prochains jours."
    )


def compact_digest_for_prompt(payload: dict) -> dict:
    """Reduce prompt size to improve Ollama response latency/reliability."""
    highlights = payload.get("highlights") or []
    compact_highlights = []
    for highlight in highlights[:4]:
        compact_highlights.append(
            {
                "date": highlight.get("dream_date") or highlight.get("timestamp"),
                "nightmare": bool(highlight.get("nightmare")),
                "tags": (highlight.get("tags") or [])[:4],
                "preview": str(highlight.get("preview") or "")[:110],
            }
        )

    return {
        "days": payload.get("days"),
        "weeks_ago": payload.get("weeks_ago"),
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "total_entries": payload.get("total_entries"),
        "nightmare_entries": payload.get("nightmare_entries"),
        "nightmare_ratio": payload.get("nightmare_ratio"),
        "tension_level": payload.get("tension_level"),
        "top_tags": (payload.get("top_tags") or [])[:8],
        "top_words": (payload.get("top_words") or [])[:10],
        "daily": payload.get("daily") or [],
        "highlights": compact_highlights,
    }


def digest_brief_for_prompt(payload: dict) -> str:
    """Build a compact textual brief for local CPU LLMs."""
    top_tags = (
        ", ".join([str(tag) for tag, _ in (payload.get("top_tags") or [])[:6]])
        or "none"
    )
    top_words = (
        ", ".join([str(word) for word, _ in (payload.get("top_words") or [])[:8]])
        or "none"
    )
    highlights = payload.get("highlights") or []
    highlight_lines = []
    for highlight in highlights[:3]:
        date = highlight.get("dream_date") or highlight.get("timestamp") or "unknown-date"
        tags = ", ".join((highlight.get("tags") or [])[:3])
        preview = str(highlight.get("preview") or "").replace("\n", " ").strip()[:90]
        nightmare = "yes" if highlight.get("nightmare") else "no"
        highlight_lines.append(
            f"- {date} | nightmare={nightmare} | tags={tags or 'none'} | {preview}"
        )

    lines = [
        f"window: {payload.get('window_start')} -> {payload.get('window_end')}",
        f"days: {payload.get('days')}",
        f"total_entries: {payload.get('total_entries')}",
        f"nightmare_entries: {payload.get('nightmare_entries')}",
        f"nightmare_ratio: {payload.get('nightmare_ratio')}",
        f"tension_level: {payload.get('tension_level')}",
        f"top_tags: {top_tags}",
        f"top_words: {top_words}",
        "highlights:",
        *(highlight_lines if highlight_lines else ["- none"]),
    ]
    return "\n".join(lines)


def render_digest_prompt(
    payload: dict,
    inputs: dict,
    default_inputs: dict,
    profile: str = "",
    addressing: str = "",
    logger=None,
) -> str:
    """Render a weekly digest prompt from configured inputs with a fallback."""
    digest_cfg = inputs.get("digest", {})
    template = digest_cfg.get(
        "weekly_summary_template",
        default_inputs["digest"]["weekly_summary_template"],
    )
    compact_payload = compact_digest_for_prompt(payload)
    digest_json = json.dumps(compact_payload, ensure_ascii=False, indent=2)
    prompt_brief = digest_brief_for_prompt(payload)
    if profile and "{user_profile}" not in template:
        template = (
            f"{template}\n\n"
            "Contexte utilisateur (a prendre en compte dans le digest):\n"
            "{user_profile}"
        )
    if addressing and "{user_addressing}" not in template:
        template = f"{template}\n\n" "Consigne d'adresse:\n" "{user_addressing}"
    try:
        return template.format(
            days=payload.get("days"),
            digest_json=digest_json,
            compact_brief=prompt_brief,
            weeks_ago=payload.get("weeks_ago"),
            window_start=payload.get("window_start"),
            window_end=payload.get("window_end"),
            user_profile=profile,
            user_addressing=addressing,
        )
    except Exception as error:
        if logger:
            logger.warning(f"Invalid digest prompt template; using default. Error: {error}")
        fallback = default_inputs["digest"]["weekly_summary_template"]
        if profile and "{user_profile}" not in fallback:
            fallback = f"{fallback}\n\n" "Contexte utilisateur:\n" "{user_profile}"
        if addressing and "{user_addressing}" not in fallback:
            fallback = f"{fallback}\n\n" "Consigne d'adresse:\n" "{user_addressing}"
        return fallback.format(
            days=payload.get("days"),
            digest_json=digest_json,
            user_profile=profile,
            user_addressing=addressing,
        )