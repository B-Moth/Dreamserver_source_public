from unittest.mock import patch

from api.config import deep_merge_dict
from api.profile import (
    empty_user_profile,
    load_user_profile,
    save_user_profile,
    sanitize_user_profile,
    user_addressing_instruction,
    user_profile_for_prompt,
    user_profile_signature,
)


def test_deep_merge_preserves_defaults_and_overrides_nested_values():
    merged = deep_merge_dict(
        {"digest": {"temperature": 0.2, "limit": 10}, "keep": True},
        {"digest": {"temperature": 0.7}, "new": "value"},
    )

    assert merged == {
        "digest": {"temperature": 0.7, "limit": 10},
        "keep": True,
        "new": "value",
    }


def test_sanitize_profile_applies_field_limits_and_timestamp():
    profile = sanitize_user_profile(
        {
            "first_name": " A " * 100,
            "other_notes": "notes " * 200,
            "ignored": "value",
        }
    )

    assert len(profile["first_name"]) == 80
    assert len(profile["other_notes"]) == 500
    assert profile["updated_at"]
    assert "ignored" not in profile


def test_profile_round_trip_uses_sanitized_loaded_values(tmp_path):
    path = tmp_path / "user_profile.json"
    saved = sanitize_user_profile(
        {"first_name": "Alex", "other_notes": "A note", "updated_at": "ignored"}
    )

    with patch("api.profile.profile_path", return_value=path):
        save_user_profile(saved)
        loaded = load_user_profile()

    assert loaded["first_name"] == "Alex"
    assert loaded["other_notes"] == "A note"
    assert loaded["updated_at"] == saved["updated_at"]


def test_missing_profile_returns_empty_shape(tmp_path):
    with patch("api.profile.profile_path", return_value=tmp_path / "missing.json"):
        profile = load_user_profile()

    assert profile == empty_user_profile()


def test_prompt_context_and_addressing_use_saved_profile(tmp_path):
    path = tmp_path / "user_profile.json"
    profile = sanitize_user_profile(
        {"first_name": "Alex", "pronouns": "iel", "pet": "Milo"}
    )

    with patch("api.profile.profile_path", return_value=path):
        save_user_profile(profile)
        context = user_profile_for_prompt()
        addressing = user_addressing_instruction()

    assert "- First name: Alex" in context
    assert "- Pet: Milo" in context
    assert 'Utilise le prenom "Alex"' in addressing
    assert 'utilise explicitement "iel"' in addressing


def test_profile_signature_ignores_updated_at(tmp_path):
    path = tmp_path / "user_profile.json"
    first = sanitize_user_profile({"first_name": "Alex"})
    second = dict(first, updated_at="different")

    with patch("api.profile.profile_path", return_value=path):
        save_user_profile(first)
        first_signature = user_profile_signature()
        save_user_profile(second)
        second_signature = user_profile_signature()

    assert first_signature == second_signature