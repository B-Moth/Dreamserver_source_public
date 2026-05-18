"""
interpretation.py — helpers for building interpretation prompts and signatures

These are pure helpers that avoid importing `api.server` to prevent circular
imports. The server will pass config/inputs/profile/addressing values when
calling them.
"""
import hashlib
import json
from typing import Any

from api.utils import _inject_user_profile_addressing, _word_overlap_ratio as utils_word_overlap_ratio
from typing import Callable


def build_interpreter_prompt(
    interpreter_key: str,
    text: str,
    inputs: dict[str, Any],
    fallback_prompt: str,
    profile: str,
    addressing: str,
    profile_block_label: str | None = None,
    addressing_block_label: str | None = None,
) -> str:
    prompts = inputs.get("interpretation", {}).get("prompts", {})
    template = prompts.get(interpreter_key, fallback_prompt)
    template = _inject_user_profile_addressing(
        template,
        profile,
        addressing,
        profile_block_label=profile_block_label,
        addressing_block_label=addressing_block_label,
    )
    return template.format(text=text, user_profile=profile, user_addressing=addressing)


def interpreter_prompt_signature(
    interpreter_key: str,
    inputs: dict[str, Any],
    builder_version: str,
    user_profile_sig: str,
    fallback_prompts: dict[str, str],
) -> str:
    prompts = inputs.get("interpretation", {}).get("prompts", {})
    payload = {
        "interpreter": interpreter_key,
        "builder_version": builder_version,
        "primary": prompts.get(interpreter_key, fallback_prompts[interpreter_key]),
        "compact": inputs.get("interpretation", {}).get(
            "compact_template", fallback_prompts.get("compact")
        ),
        "anti": inputs.get("interpretation", {}).get(
            "anti_paraphrase_template", fallback_prompts.get("anti")
        ),
        "user_profile_sig": user_profile_sig,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compact_interpret_prompt(
    interpreter_name: str,
    text: str,
    inputs: dict[str, Any],
    profile: str,
    addressing: str,
    profile_block_label: str | None = None,
    addressing_block_label: str | None = None,
) -> str:
    template = inputs.get("interpretation", {}).get(
        "compact_template", None
    )
    if template is None:
        template = (
            'Tu es {interpreter_name}. Interprète ce rêve en 2 phrases courtes, '
            'claires et concrètes, sans introduction.\n\nRêve: "{text}"'
        )
    template = _inject_user_profile_addressing(
        template,
        profile,
        addressing,
        profile_block_label=profile_block_label,
        addressing_block_label=addressing_block_label,
    )
    return template.format(
        interpreter_name=interpreter_name,
        text=text,
        user_profile=profile,
        user_addressing=addressing,
    )


def anti_paraphrase_prompt(
    interpreter_name: str,
    text: str,
    inputs: dict[str, Any],
    profile: str,
    addressing: str,
    profile_block_label: str | None = None,
    addressing_block_label: str | None = None,
) -> str:
    compact = " ".join((text or "").split())[:700]
    template = inputs.get("interpretation", {}).get(
        "anti_paraphrase_template", None
    )
    if template is None:
        template = (
            'Tu es {interpreter_name}. INTERDIT: résumer, reformuler ou citer les scènes du rêve. '
            "Réponds en 3 lignes courtes: (1) dynamique émotionnelle, (2) sens latent, (3) micro-action concrète aujourd'hui.\n\n"
            'Rêve: "{compact_text}"'
        )
    template = _inject_user_profile_addressing(
        template,
        profile,
        addressing,
        profile_block_label=profile_block_label,
        addressing_block_label=addressing_block_label,
    )
    return template.format(
        interpreter_name=interpreter_name,
        text=text,
        compact_text=compact,
        user_profile=profile,
        user_addressing=addressing,
    )


def local_interpretation_fallback(interpreter_key: str, text: str) -> str:
    fallback_by_style = {
        "fool": (
            "Ton rêve semble pointer un décalage entre ce que tu contrôles et ce que tu ressens. "
            "Le comique ici sert souvent de soupape: il montre une tension réelle sous une forme légère. "
            "Aujourd'hui, transforme cette tension en une petite décision concrète."
        ),
        "freud": (
            "Ce rêve évoque probablement un conflit entre désir et contrainte interne. "
            "La charge émotionnelle suggère un besoin de reconnaître ce que tu évites encore. "
            "Observe les émotions dominantes: elles indiquent probablement le vrai conflit psychique."
        ),
        "cassandra": (
            "Ce songe semble annoncer un passage intérieur plutôt qu'un simple souvenir de la journée. "
            "Le rêve semble parler d'un passage: quitter une forme ancienne pour une plus juste. "
            "Écoute ce qui revient en boucle, c'est souvent la clef du message."
        ),
        "oracle": (
            "Ce rêve te rappelle une chose essentielle: tu avances, même dans le flou. "
            "Il invite à faire confiance à ton ressenti immédiat et à garder un geste simple, concret, aujourd'hui. "
            "Ce que tu cherches se clarifie pas à pas."
        ),
    }
    return fallback_by_style.get(interpreter_key, fallback_by_style["oracle"])


def word_overlap_ratio(source: str, candidate: str) -> float:
    return utils_word_overlap_ratio(source, candidate)


def run_interpretation_job(
    entry_dir,
    timestamp: str,
    interpreter_key: str,
    text: str,
    job_key: str,
    worker_token: int,
    current_prompt_signature: str,
    load_config_fn: Callable[[], dict],
    is_job_current_fn: Callable[[str, int], bool],
    write_interpretation_fn: Callable,
    normalize_timeout_fn: Callable,
):
    """Run the interpretation attempts and call `write_interpretation_fn` on success.

    Parameters are passed in to keep this module independent from `server.py`.
    Returns: (success: bool, error_message: str | None)
    """
    import time

    started_at = time.perf_counter()

    def elapsed_seconds() -> float:
        return round(max(0.0, time.perf_counter() - started_at), 2)

    try:
        cfg = load_config_fn()
        ollama_cfg = cfg.get("ollama", {})
        interp_cfg = cfg.get("interpretation", {})
        model = ollama_cfg.get("model", "mistral")
        host = ollama_cfg.get("host", "http://localhost:11434")
        request_timeout = normalize_timeout_fn(
            interp_cfg.get("request_timeout_seconds", 120), 120
        )
        options_primary = {
            "num_predict": int(interp_cfg.get("num_predict", 180)),
            "temperature": float(interp_cfg.get("temperature", 0.7)),
        }
        fallback_timeout = normalize_timeout_fn(
            interp_cfg.get("fallback_timeout_seconds", 60), 60
        )
        fallback_max_chars = int(interp_cfg.get("fallback_max_chars", 900))
        options_fallback = {
            "num_predict": int(interp_cfg.get("fallback_num_predict", 96)),
            "temperature": float(interp_cfg.get("fallback_temperature", 0.6)),
        }
        allow_local_fallback = bool(interp_cfg.get("allow_local_fallback", True))
        max_overlap_ratio = float(interp_cfg.get("max_source_overlap_ratio", 0.58))

        import requests as req

        # Attempt prompts: primary, compact fallback, and anti-paraphrase.
        inputs = load_config_fn().get("mistral_inputs", {}) if load_config_fn else {}

        attempts = [
            {
                "name": "primary",
                "prompt": build_interpreter_prompt(
                    interpreter_key,
                    text,
                    inputs or {},
                    "",
                    "",
                    "",
                ),
                "options": options_primary,
                "timeout": request_timeout,
            },
            {
                "name": "fallback",
                "prompt": compact_interpret_prompt(interpreter_key, text[:fallback_max_chars], inputs or {}, "", ""),
                "options": options_fallback,
                "timeout": fallback_timeout,
            },
            {
                "name": "anti",
                "prompt": anti_paraphrase_prompt(interpreter_key, text, inputs or {}, "", ""),
                "options": options_fallback,
                "timeout": fallback_timeout,
            },
        ]

        last_error = None
        for attempt in attempts:
            try:
                response = req.post(
                    f"{host}/api/generate",
                    json={
                        "model": model,
                        "prompt": attempt["prompt"],
                        "stream": False,
                        "options": attempt["options"],
                    },
                    timeout=attempt["timeout"],
                )
            except Exception as e:
                last_error = f"{attempt['name']} error: {e}"
                continue

            if response.status_code != 200:
                last_error = f"{attempt['name']} HTTP {response.status_code}"
                continue

            result = response.json().get("response", "").strip()
            if result.startswith('"') and result.endswith('"'):
                result = result[1:-1]

            if result:
                overlap_ratio = word_overlap_ratio(text, result)
                if overlap_ratio > max_overlap_ratio:
                    last_error = (
                        f"{attempt['name']} too close to source (overlap={overlap_ratio:.2f})"
                    )
                    continue

                if not is_job_current_fn(job_key, worker_token):
                    return False, None
                # Write result via provided callback.
                write_interpretation_fn(
                    entry_dir,
                    interpreter_key,
                    result,
                    source="mistral",
                    generation_seconds=elapsed_seconds(),
                    prompt_signature=current_prompt_signature,
                )
                return True, None

            last_error = f"{attempt['name']} empty response"

        if allow_local_fallback:
            local_text = local_interpretation_fallback(interpreter_key, text)
            if not is_job_current_fn(job_key, worker_token):
                return False, None
            write_interpretation_fn(
                entry_dir,
                interpreter_key,
                local_text,
                source="fallback",
                generation_seconds=elapsed_seconds(),
                prompt_signature=current_prompt_signature,
            )
            return True, None

        return False, last_error
    except Exception as e:
        return False, str(e)
