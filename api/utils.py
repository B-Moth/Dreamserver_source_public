"""Small utility helpers extracted from server for clarity.

Keep this module minimal to avoid circular imports with `api.server`.
"""
from __future__ import annotations

import re
from typing import List

# Compiled regex patterns reused across the codebase.
_TERM_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]{1,}", re.UNICODE)
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]{3,}", re.UNICODE)
_WORD_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ']{4,}", re.UNICODE)


def term_findall(value: str) -> List[str]:
    return [t for t in _TERM_RE.findall(str(value or "").lower())]


def token_findall(text: str) -> List[str]:
    return _TOKEN_RE.findall(text)


def word_token_findall(text: str) -> List[str]:
    return _WORD_TOKEN_RE.findall(text)


def _word_overlap_ratio(source: str, candidate: str) -> float:
    """Share of candidate lexical tokens that also appear in source."""
    src_tokens = set(word_token_findall((source or "").lower()))
    cand_tokens = word_token_findall((candidate or "").lower())
    if not src_tokens or not cand_tokens:
        return 0.0
    overlap = sum(1 for tok in cand_tokens if tok in src_tokens)
    return overlap / max(len(cand_tokens), 1)


def _inject_user_profile_addressing(
    template: str,
    user_profile: str,
    user_addressing: str,
    profile_block_label: str | None = None,
    addressing_block_label: str | None = None,
) -> str:
    """Inject user profile and addressing blocks into a prompt template when missing.

    This mirrors the helper moved from server and centralizes prompt injection.
    """
    injected_blocks = []
    if addressing_block_label is None:
        addressing_block_label = "Consigne d'adresse prioritaire:"
    if profile_block_label is None:
        profile_block_label = "Contexte utilisateur:"

    if user_addressing and "{user_addressing}" not in template:
        injected_blocks.append(f"{addressing_block_label}\n{{user_addressing}}")
    if user_profile and "{user_profile}" not in template:
        injected_blocks.append(f"{profile_block_label}\n{{user_profile}}")

    if injected_blocks:
        template = "\n\n".join(injected_blocks + [template])
    return template
