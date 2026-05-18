"""Dream Map helpers and heuristics extracted from server.

This module is self-contained and avoids importing `api.server` to prevent
circular imports.
"""
from __future__ import annotations

from typing import List
import re
from pathlib import Path
import json

from api.utils import term_findall, token_findall
import unicodedata

# Optional spaCy POS tagger for French. If available, prefer it for more
# accurate noun/adjective detection; otherwise fall back to suffix heuristics.
SPACY_NLP = None
try:
    import spacy

    try:
        SPACY_NLP = spacy.load("fr_core_news_sm")
    except Exception:
        try:
            SPACY_NLP = spacy.load("fr_core_news_md")
        except Exception:
            SPACY_NLP = None
except Exception:
    SPACY_NLP = None


def _normalize_tag(tag: str) -> str:
    # Normalize, strip, lowercase and remove accents for stable matching.
    s = str(tag or "").strip().lower()
    # Unicode normalize and strip diacritics
    nkfd = unicodedata.normalize("NFKD", s)
    without_accents = "".join(ch for ch in nkfd if not unicodedata.combining(ch))
    return without_accents


# Word class lists used to exclude non-content tokens.
_DREAM_MAP_PRONOUNS = {
    "je", "j", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "m", "te", "t", "se", "s", "le", "la", "les", "lui", "leur",
    "eux", "en", "y", "ce", "cet", "cette", "ces",
    "cela", "ça", "ca", "celui", "celle", "ceux", "celles",
    "mien", "tien", "sien", "notre", "votre", "leur", "mon", "ton", "son",
    "ma", "ta", "sa", "mes", "tes", "ses", "leurs", "moi", "toi", "soi",
    "their", "them", "they", "he", "she", "we", "you", "i",
}

_DREAM_MAP_PREPOSITIONS = {
    "a", "à", "de", "du", "des", "d", "l", "au", "aux", "par", "pour", "sur", "sous", "dans",
    "avec", "sans", "entre", "vers", "chez", "apres", "après", "avant", "pendant", "selon", "contre",
    "durant", "parmi", "depuis", "jusque", "jusqu", "hors", "via",
}

_DREAM_MAP_INTERJECTIONS = {
    "ah", "oh", "eh", "hein", "hélas", "helas", "ouf", "aie", "oups", "bah", "bof", "hum",
    "bravo", "zut", "holà", "hola", "yo", "hey",
}

_DREAM_MAP_ADVERBS = {
    "très", "tres", "si", "bien", "mal", "plus", "moins", "encore", "deja", "déjà", "jamais",
    "toujours", "souvent", "rarement", "vite", "lentement", "ici", "là", "ailleurs",
    "presque", "assez", "tellement", "seulement", "vraiment", "beaucoup", "peu", "trop", "non", "oui",
}

_DREAM_MAP_COMMON_VERBS = {
    "etre", "être", "avoir", "faire", "aller", "venir", "voir", "savoir", "pouvoir", "vouloir",
    "dire", "mettre", "prendre", "donner", "partir", "laisser", "arriver", "passer", "devoir",
    "penser", "sembler", "rester", "sentir", "rêver", "reve", "regarder", "parler", "aimer", "dormir",
}

_DREAM_MAP_ALLOWED_SUFFIXES = (
    "tion", "sion", "aison", "ure", "ité", "ite", "esse", "ance", "ence", "isme", "iste", "eur",
    "euse", "eux", "ique", "able", "ible", "if", "ive", "al", "ale", "el", "elle", "ain", "aine",
    "ien", "ienne", "ois", "oise", "ard", "arde", "ot", "ote", "in", "ine", "âtre", "ette", "erie",
)

_DREAM_MAP_VERB_SUFFIXES = (
    "er", "ers", "ez", "ais", "ait", "aient", "ons", "ont", "ant", "issant", "ir", "is", "it",
    "issent", "irais", "irait", "ira", "iront", "iraient", "re", "oir", "ue", "ées", "ée", "és", "ent",
)

_DREAM_MAP_EXCLUDED_WORDS = set().union(
    _DREAM_MAP_PRONOUNS,
    _DREAM_MAP_PREPOSITIONS,
    _DREAM_MAP_INTERJECTIONS,
    _DREAM_MAP_ADVERBS,
    _DREAM_MAP_COMMON_VERBS,
    {
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "ou", "mais", "donc",
        "ni", "car", "que", "qui", "quoi", "dont", "où", "ce", "cet", "cette", "ces", "mon",
        "ton", "son", "mes", "tes", "ses", "nos", "vos", "leurs", "au", "aux", "pas", "ne",
        "rien", "personne", "tout", "tous", "toute", "toutes", "chaque", "aucun", "aucune",
    },
)


def _dream_map_split_terms(value: str) -> List[str]:
    return [term.strip("-_'’") for term in term_findall(value) if term.strip("-_'’")]


def _dream_map_is_content_word(term: str) -> bool:
    word = _normalize_tag(term)
    if not word or len(word) < 2:
        return False
    if any(ch.isdigit() for ch in word):
        return False
    if word in _DREAM_MAP_EXCLUDED_WORDS:
        return False
    # Prefer spaCy POS tags when available for robust noun/adjective filtering.
    if SPACY_NLP is not None:
        try:
            doc = SPACY_NLP(word)
            tok = doc[0] if len(doc) > 0 else None
            if tok is None:
                return False
            # Accept nouns and adjectives only.
            return tok.pos_ in {"NOUN", "ADJ"}
        except Exception:
            # Fall back to heuristics on any spaCy error.
            pass

    # Heuristic fallback: filter obvious verbs by suffix, then accept by suffix or length.
    if any(word.endswith(suffix) for suffix in _DREAM_MAP_VERB_SUFFIXES):
        return False
    return any(word.endswith(suffix) for suffix in _DREAM_MAP_ALLOWED_SUFFIXES) or len(word) >= 3


def _dream_map_is_keyword(value: str) -> bool:
    terms = _dream_map_split_terms(value)
    if not terms:
        return False
    return any(_dream_map_is_content_word(term) for term in terms)


def _dream_map_collect_tags(entries_dir: Path) -> List[str]:
    tags = set()
    for entry in entries_dir.iterdir():
        if not entry.is_dir():
            continue

        meta_file = entry / "meta.json"
        if not meta_file.exists():
            continue

        try:
            with open(meta_file) as f:
                meta = json.load(f)
        except Exception:
            continue

        for tag in meta.get("tags", []) or []:
            normalized = _normalize_tag(tag)
            if normalized and _dream_map_is_keyword(normalized):
                tags.add(normalized)

        # Additionally, if spaCy is available, extract nouns/adjectives from transcripts
        # to enrich the tag set with content words found in user texts.
        if SPACY_NLP is not None:
            for fname in [
                "transcript_user.txt",
                "transcript_corrected.txt",
                "transcript_raw.txt",
            ]:
                f = entry / fname
                if not f.exists():
                    continue
                try:
                    text = f.read_text().strip()
                except Exception:
                    continue
                if not text:
                    continue
                try:
                    doc = SPACY_NLP(text)
                    for tok in doc:
                        if tok.is_alpha and tok.pos_ in {"NOUN", "ADJ"}:
                            w = tok.lemma_.lower().strip("-_'’")
                            if w and _dream_map_is_keyword(w):
                                tags.add(w)
                except Exception:
                    # If the model fails on longer texts, skip enrichment for this entry.
                    pass

    return sorted(tags)
