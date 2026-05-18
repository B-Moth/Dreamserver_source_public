import inspect
import sys
import json
from pathlib import Path

# Ensure repository root is on sys.path for imports during tests.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

import api.dream_map as dm


def test_heuristic_filters():
    # Heuristic: common noun is accepted, verb is rejected
    assert dm._dream_map_is_content_word("maison") is True
    assert dm._dream_map_is_content_word("aller") is False


def test_spacy_mocked_token_detection(monkeypatch):
    class Token:
        def __init__(self, text, pos_):
            self.text = text
            self.lemma_ = text
            self.pos_ = pos_

    def fake_nlp(text):
        # return noun for 'chien', verb for 'courir'
        if "chien" in text:
            return [Token("chien", "NOUN")]
        if "courir" in text:
            return [Token("courir", "VERB")]
        return []

    monkeypatch.setattr(dm, "SPACY_NLP", fake_nlp)

    assert dm._dream_map_is_content_word("chien") is True
    assert dm._dream_map_is_content_word("courir") is False


def test_collect_tags_with_spacy_enrichment(tmp_path, monkeypatch):
    # Prepare a fake entry with a transcript
    entries = tmp_path / "entries"
    entries.mkdir()
    e = entries / "2026-01-01_00h00"
    e.mkdir()
    meta = {"timestamp": "2026-01-01_00h00", "tags": ["rêve"]}
    (e / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    (e / "transcript_user.txt").write_text("Je vois un chien qui court dans la maison.")

    class Token:
        def __init__(self, lemma, pos_):
            self.lemma_ = lemma
            self.pos_ = pos_
            self.is_alpha = True

    def fake_nlp(text):
        # return tokens: chien (NOUN), courir (VERB), maison (NOUN)
        return [Token("chien", "NOUN"), Token("court", "VERB"), Token("maison", "NOUN")]

    monkeypatch.setattr(dm, "SPACY_NLP", fake_nlp)

    tags = dm._dream_map_collect_tags(entries)
    # Should include lemmas 'chien' and 'maison'
    assert "chien" in tags
    assert "maison" in tags
