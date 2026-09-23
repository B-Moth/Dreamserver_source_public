from api.interpretation import (
    anti_paraphrase_prompt,
    build_interpreter_prompt,
    compact_interpret_prompt,
    interpreter_prompt_signature,
    word_overlap_ratio,
)


def test_build_interpreter_prompt_injects_missing_context():
    prompt = build_interpreter_prompt(
        "oracle",
        "Une porte bleue.",
        {"interpretation": {"prompts": {"oracle": "Reve: {text}"}}},
        "Fallback: {text}",
        "First name: Alex",
        "Use tu.",
    )

    assert "Une porte bleue." in prompt
    assert "First name: Alex" in prompt
    assert "Use tu." in prompt


def test_compact_and_anti_paraphrase_prompts_include_text():
    compact = compact_interpret_prompt(
        "Oracle", "Une porte bleue.", {}, "", ""
    )
    anti = anti_paraphrase_prompt("Oracle", "Une porte bleue.", {}, "", "")

    assert "Une porte bleue." in compact
    assert "Une porte bleue." in anti


def test_interpreter_prompt_signature_changes_with_profile():
    fallback = {"oracle": "Fallback {text}", "compact": "compact", "anti": "anti"}
    first = interpreter_prompt_signature("oracle", {}, "v1", "profile-a", fallback)
    second = interpreter_prompt_signature("oracle", {}, "v1", "profile-b", fallback)

    assert first != second


def test_word_overlap_ratio_measures_candidate_words():
    assert word_overlap_ratio("blue door and sea", "blue sea") == 1.0
    assert word_overlap_ratio("blue door", "red sea") == 0.0