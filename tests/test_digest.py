from api.digest import (
    compact_digest_for_prompt,
    digest_brief_for_prompt,
    fallback_digest_summary,
    render_digest_prompt,
)


def sample_payload():
    return {
        "days": 7,
        "weeks_ago": 0,
        "window_start": "2026-09-14",
        "window_end": "2026-09-20",
        "total_entries": 2,
        "nightmare_entries": 1,
        "nightmare_ratio": 0.5,
        "tension_level": "medium",
        "top_tags": [("eau", 4), ("maison", 2)],
        "top_words": [("eau", 5), ("porte", 2)],
        "daily": [{"date": "2026-09-15", "count": 1}],
        "highlights": [
            {
                "dream_date": "2026-09-15T07:00:00",
                "timestamp": "2026-09-15_07h00",
                "nightmare": True,
                "tags": ["eau", "maison"],
                "preview": "Une longue scene pres de la mer.",
            }
        ],
    }


def test_fallback_summary_describes_populated_digest():
    summary = fallback_digest_summary(sample_payload())

    assert "2 reves" in summary
    assert "medium" in summary
    assert "eau" in summary
    assert "porte" in summary


def test_fallback_summary_handles_empty_digest():
    summary = fallback_digest_summary({"total_entries": 0})

    assert "aucun reve transcrit" in summary


def test_compact_digest_limits_prompt_payload():
    payload = sample_payload()
    payload["highlights"] = [
        {"timestamp": str(index), "preview": "x" * 200, "tags": list(range(8))}
        for index in range(6)
    ]

    compact = compact_digest_for_prompt(payload)

    assert len(compact["highlights"]) == 4
    assert len(compact["highlights"][0]["tags"]) == 4
    assert len(compact["highlights"][0]["preview"]) == 110
    assert compact["top_tags"] == [("eau", 4), ("maison", 2)]


def test_digest_brief_contains_compact_summary_lines():
    brief = digest_brief_for_prompt(sample_payload())

    assert "window: 2026-09-14 -> 2026-09-20" in brief
    assert "top_tags: eau, maison" in brief
    assert "nightmare=yes" in brief


def test_render_digest_prompt_injects_profile_and_addressing():
    payload = sample_payload()
    defaults = {"digest": {"weekly_summary_template": "fallback {days}"}}
    inputs = {
        "digest": {
            "weekly_summary_template": "{days}|{user_profile}|{user_addressing}"
        }
    }

    prompt = render_digest_prompt(
        payload,
        inputs,
        defaults,
        profile="First name: Alex",
        addressing="Use tu.",
    )

    assert prompt == "7|First name: Alex|Use tu."


def test_render_digest_prompt_falls_back_for_invalid_template():
    class Logger:
        messages = []

        def warning(self, message):
            self.messages.append(message)

    logger = Logger()
    defaults = {"digest": {"weekly_summary_template": "safe {days}"}}
    prompt = render_digest_prompt(
        sample_payload(),
        {"digest": {"weekly_summary_template": "{missing}"}},
        defaults,
        logger=logger,
    )

    assert prompt == "safe 7"
    assert logger.messages