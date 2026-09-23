"""Dream Map normalization and French content-word heuristics."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from api.utils import term_findall


def normalize_tag(tag: str) -> str:
    value = str(tag or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


EXCLUDED_WORDS = set(
    """je j tu il elle on nous vous ils elles me m te t se s le la les lui leur eux en y ce cet cette ces cela ca celui celle ceux celles mien tien sien notre votre mon ton son ma ta sa mes tes ses leurs moi toi soi their them they he she we you i
    a à de du des d l au aux par pour sur sous dans avec sans entre vers chez apres après avant pendant selon contre durant parmi depuis jusque jusqu hors via
    ah oh eh hein helas hélas ouf aie oups bah bof hum bravo zut hola yo hey
    tres très si bien mal plus moins encore deja déjà jamais toujours souvent rarement vite lentement ici là ailleurs presque assez tellement seulement vraiment beaucoup peu trop non oui
    etre être avoir faire aller venir voir savoir pouvoir vouloir falloir dire mettre prendre donner partir laisser arriver passer devoir penser sembler rester sentir rever rêve regarder parler aimer dormir marcher courir ouvrir fermer trouver montrer tourner tomber peux peut vais va vont viens vient fais fait font dis dit suis es est sommes êtes etes sont avais avait avaient allais allait allons allez allaient faisais faisait faisaient prends prend prennent
    et mais donc or ni car que qui quoi dont ou ce c cet cette ces mon ton son mes tes ses nos vos leurs leur pas ne rien personne tout tous toute toutes chaque aucun aucune
    """.split()
)

ALLOWED_SUFFIXES = (
    "tion", "sion", "aison", "ure", "ité", "ite", "esse", "ance", "ence",
    "isme", "iste", "eur", "euse", "eux", "ique", "able", "ible", "if", "ive",
    "al", "ale", "el", "elle", "ain", "aine", "ien", "ienne", "ois", "oise",
    "ard", "arde", "ot", "ote", "in", "ine", "âtre", "ette", "erie",
)

VERB_SUFFIXES = (
    "er", "ers", "ez", "ais", "ait", "aient", "ons", "ont", "ant", "issant",
    "ir", "is", "it", "issent", "irais", "irait", "ira", "iront", "iraient",
    "re", "oir", "ue", "ées", "ée", "és", "ent",
)


def split_terms(value: str) -> list[str]:
    return [term.strip("-_'’") for term in term_findall(value) if term.strip("-_'’")]


def is_content_word(term: str) -> bool:
    word = normalize_tag(term)
    if not word or len(word) < 3 or any(char.isdigit() for char in word):
        return False
    if word in EXCLUDED_WORDS or any(word.endswith(suffix) for suffix in VERB_SUFFIXES):
        return False
    return any(word.endswith(suffix) for suffix in ALLOWED_SUFFIXES) or len(word) >= 3


def is_keyword(value: str) -> bool:
    return any(is_content_word(term) for term in split_terms(value))


def collect_tags(entries_dir: Path) -> list[str]:
    tags = set()
    for entry in entries_dir.iterdir():
        if not entry.is_dir():
            continue
        meta_file = entry / "meta.json"
        if not meta_file.exists():
            continue
        try:
            with open(meta_file) as meta_handle:
                meta = json.load(meta_handle)
        except Exception:
            continue
        for tag in meta.get("tags", []) or []:
            normalized = normalize_tag(tag)
            if normalized and is_keyword(normalized):
                tags.add(normalized)
    return sorted(tags)