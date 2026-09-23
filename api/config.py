"""Configuration and deployment paths for Dreamserver."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / "dreamserver" / "config.yaml"
MISTRAL_INPUTS_FILE = Path.home() / "dreamserver" / "config" / "mistral_inputs.yaml"
SEMANTIC_GROUPS_FILE = Path.home() / "dreamserver" / "storage" / "semantic_groups.json"
DIGEST_SUMMARIES_DIR = Path.home() / "dreamserver" / "storage" / "digest_summaries"
USER_PROFILE_FILE = Path.home() / "dreamserver" / "storage" / "user_profile.json"

DEFAULT_MISTRAL_INPUTS = {
    "interpretation": {
        "prompts": {
            "fool": (
                "Tu es Le Fou, interprète de rêves facétieux inspiré du fou du roi. "
                "Donne une lecture symbolique et psychologique SANS résumer le récit ni répéter les scènes. "
                "Structure: 1) tension intérieure probable, 2) angle absurde éclairant, "
                "3) mini-conseil concret pour demain. 3 phrases maximum. Pas d'introduction.\n\n"
                "Rêve: {text}"
            ),
            "freud": (
                "Tu es Sigmund, interprète de rêves analytique inspiré de Freud. "
                "Analyse SANS paraphraser le rêve: identifie le conflit psychique central, "
                "le désir/peur sous-jacent, puis une hypothèse de mécanisme (défense, déplacement, etc.). "
                "3 phrases maximum. Pas d'introduction.\n\n"
                "Rêve: {text}"
            ),
            "cassandra": (
                "Tu es Cassandre, prophétesse mystique. "
                "Interprète les symboles en profondeur SANS raconter le rêve. "
                "Donne: 1) symbole maître, 2) mouvement intérieur qu'il annonce, "
                "3) geste rituel simple pour intégrer le message. "
                "3 phrases maximum, poétiques mais claires, sans introduction.\n\n"
                "Rêve: {text}"
            ),
            "oracle": (
                "Tu es un oracle bienveillant. "
                "Interprète ce rêve SANS le reformuler: cible le besoin émotionnel principal, "
                "l'élan de transformation, et un conseil actionnable pour la journée. "
                "3 phrases maximum. Ton chaleureux, pas d'introduction.\n\n"
                "Rêve: {text}"
            ),
        },
        "compact_template": (
            "Tu es {interpreter_name}. Interprète ce rêve en 2 phrases courtes, "
            "claires et concrètes, sans introduction.\n\n"
            'Rêve: "{text}"'
        ),
        "anti_paraphrase_template": (
            "Tu es {interpreter_name}. INTERDIT: résumer, reformuler ou citer les scènes du rêve. "
            "Réponds en 3 lignes courtes: (1) dynamique émotionnelle, "
            "(2) sens latent, (3) micro-action concrète aujourd'hui.\n\n"
            'Rêve: "{compact_text}"'
        ),
    },
    "dream_map": {
        "tag_classifier_template": (
            "Tu classes un tag de rêve dans un groupe sémantique. "
            "Si aucun groupe existant n'est suffisamment proche, crée un NOUVEAU groupe court (1-3 mots). "
            'Réponds STRICTEMENT en JSON valide au format: {"group":"...","existing":true|false}. '
            "Pas de texte autour.\n\n"
            "Tag: {tag}\n"
            "Groupes existants: {groups_json}"
        )
    },
    "digest": {
        "weekly_summary_template": (
            "Tu es analyste de journal de reves. "
            "A partir du digest JSON ci-dessous, ecris un resume en 4 a 5 phrases maximum, "
            "en francais naturel, concret et utile, sans inventer de donnees. "
            "Mentionne le climat general (tension), les themes dominants et une piste d'action simple.\n\n"
            "Jours couverts: {days}\n"
            "Digest JSON: {digest_json}"
        )
    },
}


def load_config() -> dict:
    import yaml

    with open(CONFIG_FILE) as config_file:
        return yaml.safe_load(config_file)


def deep_merge_dict(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_mistral_inputs() -> dict:
    import yaml

    data = {}
    if MISTRAL_INPUTS_FILE.exists():
        try:
            with open(MISTRAL_INPUTS_FILE) as inputs_file:
                data = yaml.safe_load(inputs_file) or {}
        except Exception as error:
            log.warning(f"Failed to load mistral inputs config: {error}")
    return deep_merge_dict(DEFAULT_MISTRAL_INPUTS, data)