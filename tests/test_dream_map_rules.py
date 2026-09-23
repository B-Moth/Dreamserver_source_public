import json

from api.dream_map_rules import collect_tags, is_content_word, is_keyword, normalize_tag


def test_normalize_tag_removes_accents_and_case():
    assert normalize_tag("  Étrange  ") == "etrange"


def test_keyword_rules_exclude_verbs_and_accept_content_words():
    assert is_content_word("maison") is True
    assert is_content_word("courir") is False
    assert is_keyword("grande maison") is True


def test_collect_tags_reads_normalized_keyword_tags(tmp_path):
    entry = tmp_path / "entry"
    entry.mkdir()
    (entry / "meta.json").write_text(json.dumps({"tags": ["Émotion", "courir"]}))

    assert collect_tags(tmp_path) == ["emotion"]