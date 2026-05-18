import inspect
import sys
from pathlib import Path

# Ensure repository root is on sys.path for imports during tests.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import server
from api import utils


def test_dream_map_split_terms():
    s = "La maison-bleue d'Anna, promenade"
    terms = server._dream_map_split_terms(s)
    assert "maison" in terms or "maison-bleue" in terms


def test_dream_map_is_keyword():
    assert server._dream_map_is_keyword("maison")
    assert not server._dream_map_is_keyword("et")


def test_word_overlap_ratio():
    src = "je suis allé à la maison et j'ai vu un chien qui court"
    cand = "un chien court dans la maison"
    ratio = server._word_overlap_ratio(src, cand)
    assert 0 <= ratio <= 1
    assert ratio > 0


def test_compiled_patterns_exist():
    # Ensure compiled regex values are present and re-usable
    assert hasattr(utils, "_TERM_RE")
    assert hasattr(utils, "_TOKEN_RE")
    assert hasattr(utils, "_WORD_TOKEN_RE")
    assert inspect.isclass(utils._TERM_RE.__class__)
