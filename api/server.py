"""
server.py — FastAPI server for Sandman
Receives audio uploads from DreamCatcher
Automatically transcribes after upload
Optionally corrects after transcription
Sends push notifications when transcript is ready
Serves PWA static files over HTTPS
"""

import json
import hashlib
import logging
import re
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline.transcriber import Transcriber
from pipeline.corrector import Corrector
from notifications.push import (
    add_subscription,
    remove_subscription,
    send_transcript_ready,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [dreamserver] %(message)s")
log = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = Path.home() / "dreamserver" / "config.yaml"
MISTRAL_INPUTS_FILE = Path.home() / "dreamserver" / "config" / "mistral_inputs.yaml"
SEMANTIC_GROUPS_FILE = Path.home() / "dreamserver" / "storage" / "semantic_groups.json"
DIGEST_SUMMARIES_DIR = Path.home() / "dreamserver" / "storage" / "digest_summaries"
USER_PROFILE_FILE = Path.home() / "dreamserver" / "storage" / "user_profile.json"

_semantic_lock = threading.Lock()
_semantic_loaded = False
_semantic_tag_to_group = {}
_semantic_pending_tags = set()
_semantic_generation = 0
_digest_lock = threading.Lock()
_digest_summary_queue = {}
_digest_summary_results = {}
_digest_summary_errors = {}
_digest_job_tokens = {}
_digest_guard_lock = threading.Lock()
_digest_ollama_failures = 0
_digest_ollama_cooldown_until = 0.0
_maintenance_last_run_at = 0.0
_fallback_retry_lock = threading.Lock()
_fallback_retry_queue = []
_fallback_retry_pending = set()

from api.utils import (
    token_findall,
    term_findall,
    word_token_findall,
)
from api.interpretation import (
    build_interpreter_prompt,
    interpreter_prompt_signature,
    compact_interpret_prompt,
    anti_paraphrase_prompt,
    local_interpretation_fallback,
    run_interpretation_job,
    word_overlap_ratio,
)
from api.dream_map import (
    _dream_map_collect_tags,
    _dream_map_is_content_word,
    _dream_map_is_keyword,
)


def _fallback_retry_key(job: dict) -> str:
    if job.get("kind") == "digest":
        return f"digest:{job.get('days')}:{job.get('weeks_ago')}"
    if job.get("kind") == "interpret":
        return f"interpret:{job.get('timestamp')}:{job.get('interpreter')}"
    return f"unknown:{job}"


def _enqueue_fallback_retry(job: dict):
    key = _fallback_retry_key(job)
    with _fallback_retry_lock:
        if key in _fallback_retry_pending:
            return
        item = {
            **job,
            "next_try_at": float(job.get("next_try_at") or 0),
            "tries": int(job.get("tries") or 0),
        }
        _fallback_retry_queue.append(item)
        _fallback_retry_pending.add(key)


def _digest_summary_path(days: int, weeks_ago: int) -> Path:
    DIGEST_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    return DIGEST_SUMMARIES_DIR / f"weekly_{days}_w{weeks_ago}.json"


def _profile_path() -> Path:
    try:
        cfg = _load_config()
        custom = str(cfg.get("profile_file") or "").strip()
        if custom:
            p = Path(custom)
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return USER_PROFILE_FILE


def _empty_user_profile() -> dict:
    return {
        "first_name": "",
        "last_name": "",
        "pronouns": "",
        "birthday": "",
        "pet": "",
        "closest_relative": "",
        "closest_relative_status": "",
        "other_notes": "",
        "updated_at": None,
    }


def _sanitize_profile_value(value, limit: int = 280) -> str:
    v = str(value or "").strip()
    return v[:limit]


def _sanitize_user_profile(payload: dict | None) -> dict:
    data = payload or {}
    clean = _empty_user_profile()
    clean["first_name"] = _sanitize_profile_value(data.get("first_name"), 80)
    clean["last_name"] = _sanitize_profile_value(data.get("last_name"), 80)
    clean["pronouns"] = _sanitize_profile_value(data.get("pronouns"), 120)
    clean["birthday"] = _sanitize_profile_value(data.get("birthday"), 40)
    clean["pet"] = _sanitize_profile_value(data.get("pet"), 160)
    clean["closest_relative"] = _sanitize_profile_value(
        data.get("closest_relative"), 160
    )
    clean["closest_relative_status"] = _sanitize_profile_value(
        data.get("closest_relative_status"), 220
    )
    clean["other_notes"] = _sanitize_profile_value(data.get("other_notes"), 500)
    clean["updated_at"] = datetime.now().isoformat()
    return clean


def _load_user_profile() -> dict:
    p = _profile_path()
    if not p.exists():
        return _empty_user_profile()
    try:
        with open(p, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_user_profile()
        merged = _empty_user_profile()
        for k in merged.keys():
            if k == "updated_at":
                merged[k] = data.get(k)
            else:
                merged[k] = _sanitize_profile_value(
                    data.get(k), 500 if k == "other_notes" else 280
                )
        return merged
    except Exception:
        return _empty_user_profile()


def _user_profile_for_prompt() -> str:
    p = _load_user_profile()
    fields = [
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("pronouns", "Pronouns"),
        ("birthday", "Birthday"),
        ("pet", "Pet"),
        ("closest_relative", "Closest relative"),
        ("closest_relative_status", "Relative status"),
        ("other_notes", "Other relevant notes"),
    ]
    lines = []
    for key, label in fields:
        value = str(p.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _user_addressing_instruction() -> str:
    p = _load_user_profile()
    first_name = str(p.get("first_name") or "").strip()
    pronouns = str(p.get("pronouns") or "").strip()

    if not first_name and not pronouns:
        return (
            "Adresse-toi directement a l'utilisateur en deuxieme personne (tu/ton/tes)."
        )

    lines = [
        "Consignes de personnalisation prioritaires:",
        "- Ecris uniquement en francais.",
        "- Adresse-toi directement a l'utilisateur en deuxieme personne (tu/ton/tes).",
    ]
    if first_name:
        lines.append(
            f'- Utilise le prenom "{first_name}" quand tu t\'adresses a la personne.'
        )
    if pronouns:
        normalized = pronouns.lower().replace("·", "").replace(" ", "")
        lines.append(f'- Pronoms preferes: "{pronouns}".')
        lines.append(
            "- N'invente pas et ne traduis pas les pronoms "
            '(interdit: "they/them" ou "Nom/Them" si ce n\'est pas fourni).'
        )
        if "iel" in normalized:
            lines.append(
                '- Si une phrase impose la troisieme personne, utilise explicitement "iel" '
                "et garde une formulation inclusive."
            )
        else:
            lines.append(
                "- Si une phrase impose la troisieme personne, reprends exactement les pronoms fournis."
            )
    lines.append("- Ne commente pas ces consignes dans la reponse.")
    return "\n".join(lines)


def _user_profile_signature() -> str:
    p = _load_user_profile()
    payload = {
        "first_name": p.get("first_name"),
        "last_name": p.get("last_name"),
        "pronouns": p.get("pronouns"),
        "birthday": p.get("birthday"),
        "pet": p.get("pet"),
        "closest_relative": p.get("closest_relative"),
        "closest_relative_status": p.get("closest_relative_status"),
        "other_notes": p.get("other_notes"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _inject_user_profile_addressing(
    template: str,
    user_profile: str,
    user_addressing: str,
    profile_block_label: str | None = None,
    addressing_block_label: str | None = None,
) -> str:
    """Inject user profile and addressing blocks into a prompt template when missing.

    This centralizes the small, repeated logic used by interpretation prompt builders
    so changes remain local and consistent. The returned template is unformatted
    and should then be formatted with the desired keyword arguments.
    """
    injected_blocks = []
    if addressing_block_label is None:
        addressing_block_label = "Consigne d'adresse prioritaire:"
    if profile_block_label is None:
        profile_block_label = "Contexte utilisateur (a prendre en compte dans l'interpretation):"

    if user_addressing and "{user_addressing}" not in template:
        injected_blocks.append(f"{addressing_block_label}\n{{user_addressing}}")
    if user_profile and "{user_profile}" not in template:
        injected_blocks.append(f"{profile_block_label}\n{{user_profile}}")

    if injected_blocks:
        template = "\n\n".join(injected_blocks + [template])
    return template


def _load_persisted_digest_summary(days: int, weeks_ago: int):
    p = _digest_summary_path(days, weeks_ago)
    if not p.exists():
        return None
    try:
        with open(p, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if not data.get("summary"):
            return None
        persisted_profile_sig = data.get("profile_signature")
        current_profile_sig = _user_profile_signature()
        if persisted_profile_sig != current_profile_sig:
            return None
        return {
            "source": data.get("source") or "fallback",
            "summary": data.get("summary") or "",
            "digest": data.get("digest") or {},
            "created_at": data.get("created_at"),
            "generation_seconds": data.get("generation_seconds"),
            "profile_signature": data.get("profile_signature"),
        }
    except Exception:
        return None


def _persist_digest_summary(days: int, weeks_ago: int, payload: dict):
    p = _digest_summary_path(days, weeks_ago)
    to_store = {
        "source": payload.get("source"),
        "summary": payload.get("summary"),
        "digest": payload.get("digest"),
        "created_at": datetime.now().isoformat(),
        "generation_seconds": payload.get("generation_seconds"),
        "profile_signature": payload.get("profile_signature")
        or _user_profile_signature(),
    }
    with open(p, "w") as f:
        json.dump(to_store, f, ensure_ascii=False, indent=2)


def _build_persisted_fallback_result(
    days: int, weeks_ago: int, reason: str = ""
) -> dict:
    payload = _compute_weekly_digest_payload(days, weeks_ago)
    summary = _fallback_digest_summary(payload)
    if reason:
        summary = f"{summary}\n\n(note: {reason})"
    result = {
        "source": "fallback",
        "summary": summary,
        "digest": payload,
        "created_at": datetime.now().isoformat(),
        "generation_seconds": 0,
        "profile_signature": _user_profile_signature(),
    }
    _persist_digest_summary(days, weeks_ago, result)
    return result


def _interpretation_meta_path(entry_dir: Path, interpreter_key: str) -> Path:
    return entry_dir / f"interpretation_{interpreter_key}.json"


def _read_interpretation_meta(entry_dir: Path, interpreter_key: str) -> dict:
    meta_path = _interpretation_meta_path(entry_dir, interpreter_key)
    if not meta_path.exists():
        return {
            "source": "mistral",
            "generation_seconds": None,
            "prompt_signature": None,
        }
    try:
        with open(meta_path, "r") as f:
            data = json.load(f)
        source = str(data.get("source") or "mistral").strip().lower() or "mistral"
        generation_seconds = data.get("generation_seconds")
        return {
            "source": source,
            "generation_seconds": generation_seconds,
            "prompt_signature": data.get("prompt_signature"),
        }
    except Exception:
        return {
            "source": "mistral",
            "generation_seconds": None,
            "prompt_signature": None,
        }


def _read_interpretation_source(entry_dir: Path, interpreter_key: str) -> str:
    return (
        _read_interpretation_meta(entry_dir, interpreter_key).get("source") or "mistral"
    )


def _write_interpretation(
    entry_dir: Path,
    interpreter_key: str,
    text: str,
    source: str,
    generation_seconds: float | None = None,
    prompt_signature: str | None = None,
):
    txt_path = entry_dir / f"interpretation_{interpreter_key}.txt"
    txt_path.write_text(text)
    meta_path = _interpretation_meta_path(entry_dir, interpreter_key)
    payload = {
        "source": source,
        "generation_seconds": generation_seconds,
        "prompt_signature": prompt_signature,
        "updated_at": datetime.now().isoformat(),
    }
    with open(meta_path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _normalize_timeout_seconds(raw_value, default_seconds: int):
    """Return requests timeout seconds or None (no timeout) when configured <= 0."""
    try:
        v = float(raw_value)
    except Exception:
        v = float(default_seconds)
    if v <= 0:
        return None
    return v


def _digest_guard_is_cooling_down() -> bool:
    with _digest_guard_lock:
        return time.time() < _digest_ollama_cooldown_until


def _digest_guard_record_success():
    global _digest_ollama_failures, _digest_ollama_cooldown_until
    with _digest_guard_lock:
        _digest_ollama_failures = 0
        _digest_ollama_cooldown_until = 0.0


def _digest_guard_record_failure(digest_cfg: dict):
    global _digest_ollama_failures, _digest_ollama_cooldown_until
    threshold = max(1, int(digest_cfg.get("ollama_failure_threshold", 3)))
    cooldown_seconds = max(60, int(digest_cfg.get("ollama_cooldown_seconds", 900)))
    with _digest_guard_lock:
        _digest_ollama_failures += 1
        if _digest_ollama_failures >= threshold:
            _digest_ollama_cooldown_until = time.time() + cooldown_seconds


def _run_offhours_maintenance():
    config = _load_config()
    digest_cfg = config.get("digest", {})
    retention_days = max(1, int(digest_cfg.get("summary_retention_days", 45)))
    retention_seconds = retention_days * 24 * 3600
    now_ts = time.time()

    # Keep persistence bounded and avoid stale in-memory buildup.
    if DIGEST_SUMMARIES_DIR.exists():
        for p in DIGEST_SUMMARIES_DIR.glob("weekly_*.json"):
            try:
                if now_ts - p.stat().st_mtime > retention_seconds:
                    p.unlink()
            except Exception:
                pass

    with _digest_lock:
        _digest_summary_results.clear()
        _digest_summary_errors.clear()


def _maintenance_loop():
    global _maintenance_last_run_at
    while True:
        try:
            cfg = _load_config()
            mcfg = cfg.get("maintenance", {})
            if not bool(mcfg.get("enabled", True)):
                time.sleep(300)
                continue

            start_hour = int(mcfg.get("offhours_start", 2))
            end_hour = int(mcfg.get("offhours_end", 6))
            interval_minutes = max(30, int(mcfg.get("interval_minutes", 120)))
            now = datetime.now()
            hour = now.hour

            if start_hour <= end_hour:
                in_window = start_hour <= hour < end_hour
            else:
                in_window = hour >= start_hour or hour < end_hour

            should_run = in_window and (time.time() - _maintenance_last_run_at) >= (
                interval_minutes * 60
            )
            if should_run:
                _run_offhours_maintenance()
                _maintenance_last_run_at = time.time()
                log.info("Off-hours maintenance completed")
        except Exception as e:
            log.warning(f"Off-hours maintenance error: {e}")

        time.sleep(300)


_DEFAULT_MISTRAL_INPUTS = {
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


def _load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def _deep_merge_dict(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge_dict(merged[k], v)
        else:
            merged[k] = v
    return merged


def _load_mistral_inputs():
    data = {}
    if MISTRAL_INPUTS_FILE.exists():
        try:
            with open(MISTRAL_INPUTS_FILE) as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            log.warning(f"Failed to load mistral inputs config: {e}")
    return _deep_merge_dict(_DEFAULT_MISTRAL_INPUTS, data)


# ── Pipeline callbacks ─────────────────────────────────────────────────────────


def _on_transcription_complete(entry_path: Path, transcript: str):
    config = _load_config()

    meta_file = entry_path / "meta.json"
    meta = {}
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)

    send_transcript_ready(
        timestamp=entry_path.name,
        transcript_preview=transcript,
        fuzzy=meta.get("fuzzy", False),
    )

    correction_enabled = config.get("correction", {}).get("enabled", False)
    if correction_enabled:
        log.info(f"Auto-correction enabled — queuing {entry_path.name}")
        corrector.enqueue(entry_path)
    else:
        log.info(f"Auto-correction disabled — {entry_path.name} ready")


def _on_correction_complete(entry_path: Path, corrected: str):
    log.info(f"Correction complete: {entry_path.name}")


# ── Pipeline instances ─────────────────────────────────────────────────────────

transcriber = Transcriber(on_complete=_on_transcription_complete)
corrector = Corrector(on_complete=_on_correction_complete)


@app.on_event("startup")
async def startup():
    transcriber.start()
    corrector.start()
    transcriber.resume_pending()
    _ensure_semantic_store_loaded()
    threading.Thread(target=_maintenance_loop, daemon=True).start()
    config = _load_config()
    if config.get("correction", {}).get("enabled", False):
        corrector.resume_pending()
    log.info("DreamServer ready")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _verify_api_key(x_api_key: str):
    config = _load_config()
    expected = config.get("server", {}).get("api_key", "")
    if expected == "dream":
        # Development/personal mode: don't block requests on API key mismatches.
        # This avoids intermittent client lockouts (notably iOS PWA storage quirks).
        return

    provided = (x_api_key or "").strip()
    if provided == expected:
        return

    raise HTTPException(status_code=403, detail="Invalid API key")


def _normalize_dream_date(value):
    """Parse optional dream_date into ISO 8601 or return None."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dream_date (use ISO 8601)")


def _apply_dream_date_fallback(meta: dict):
    """Ensure dream_date exists for legacy entries by falling back to received_at."""
    if not isinstance(meta, dict):
        return meta
    if not meta.get("dream_date") and meta.get("received_at"):
        meta["dream_date"] = meta["received_at"]
    return meta


def _normalize_tag(tag: str) -> str:
    return str(tag or "").strip().lower()


_DREAM_MAP_PRONOUNS = {
    "je",
    "j",
    "tu",
    "il",
    "elle",
    "on",
    "nous",
    "vous",
    "ils",
    "elles",
    "me",
    "m",
    "te",
    "t",
    "se",
    "s",
    "le",
    "la",
    "les",
    "lui",
    "leur",
    "eux",
    "en",
    "y",
    "ce",
    "cet",
    "cette",
    "ces",
    "cela",
    "ça",
    "ca",
    "celui",
    "celle",
    "ceux",
    "celles",
    "mien",
    "tien",
    "sien",
    "notre",
    "votre",
    "leur",
    "mon",
    "ton",
    "son",
    "ma",
    "ta",
    "sa",
    "mes",
    "tes",
    "ses",
    "leurs",
    "moi",
    "toi",
    "soi",
    "their",
    "them",
    "they",
    "he",
    "she",
    "we",
    "you",
    "i",
}

_DREAM_MAP_PREPOSITIONS = {
    "a",
    "à",
    "de",
    "du",
    "des",
    "d",
    "l",
    "au",
    "aux",
    "par",
    "pour",
    "sur",
    "sous",
    "dans",
    "avec",
    "sans",
    "entre",
    "vers",
    "chez",
    "apres",
    "après",
    "avant",
    "pendant",
    "selon",
    "contre",
    "durant",
    "parmi",
    "sur",
    "sous",
    "chez",
    "depuis",
    "jusque",
    "jusqu",
    "hors",
    "via",
    "sur",
}

_DREAM_MAP_INTERJECTIONS = {
    "ah",
    "oh",
    "eh",
    "hein",
    "hélas",
    "helas",
    "ouf",
    "ouf",
    "aie",
    "oups",
    "bah",
    "bof",
    "hum",
    "bravo",
    "zut",
    "holà",
    "hola",
    "yo",
    "hey",
}

_DREAM_MAP_ADVERBS = {
    "très",
    "tres",
    "si",
    "bien",
    "mal",
    "plus",
    "moins",
    "encore",
    "deja",
    "déjà",
    "jamais",
    "toujours",
    "souvent",
    "rarement",
    "vite",
    "lentement",
    "vite",
    "ici",
    "là",
    "la",
    "ailleurs",
    "presque",
    "assez",
    "tellement",
    "seulement",
    "vraiment",
    "beaucoup",
    "peu",
    "trop",
    "non",
    "oui",
    "peut-être",
    "peut",
    "peutetre",
    "probablement",
    "peut_etre",
    "simplement",
    "finalement",
    "ensuite",
}

_DREAM_MAP_COMMON_VERBS = {
    "etre",
    "être",
    "avoir",
    "faire",
    "aller",
    "venir",
    "voir",
    "savoir",
    "pouvoir",
    "vouloir",
    "falloir",
    "dire",
    "mettre",
    "prendre",
    "donner",
    "venir",
    "partir",
    "laisser",
    "arriver",
    "passer",
    "devoir",
    "penser",
    "sembler",
    "rester",
    "sentir",
    "rêver",
    "reve",
    "regarder",
    "parler",
    "aimer",
    "dormir",
    "marcher",
    "courir",
    "ouvrir",
    "fermer",
    "trouver",
    "montrer",
    "tourner",
    "tomber",
    "savoir",
    "peux",
    "peut",
    "peut",
    "vais",
    "va",
    "vont",
    "viens",
    "vient",
    "fais",
    "fait",
    "font",
    "dis",
    "dit",
    "suis",
    "es",
    "est",
    "sommes",
    "êtes",
    "etes",
    "sont",
    "avais",
    "avait",
    "avaient",
    "allais",
    "allait",
    "allons",
    "allez",
    "allaient",
    "faisais",
    "faisait",
    "faisaient",
    "prends",
    "prend",
    "prennent",
}

_DREAM_MAP_ALLOWED_SUFFIXES = (
    "tion",
    "sion",
    "aison",
    "ure",
    "ité",
    "ite",
    "esse",
    "ance",
    "ence",
    "isme",
    "iste",
    "eur",
    "euse",
    "eux",
    "ique",
    "able",
    "ible",
    "if",
    "ive",
    "al",
    "ale",
    "el",
    "elle",
    "ain",
    "aine",
    "ien",
    "ienne",
    "ois",
    "oise",
    "ard",
    "arde",
    "ot",
    "ote",
    "in",
    "ine",
    "âtre",
    "ette",
    "erie",
    "erie",
    "erie",
)

_DREAM_MAP_VERB_SUFFIXES = (
    "er",
    "ers",
    "ez",
    "ais",
    "ait",
    "aient",
    "ons",
    "ont",
    "ant",
    "issant",
    "ir",
    "is",
    "it",
    "issent",
    "irais",
    "irait",
    "ira",
    "iront",
    "iraient",
    "re",
    "oir",
    "ue",
    "ées",
    "ée",
    "és",
    "ent",
)

_DREAM_MAP_EXCLUDED_WORDS = set().union(
    _DREAM_MAP_PRONOUNS,
    _DREAM_MAP_PREPOSITIONS,
    _DREAM_MAP_INTERJECTIONS,
    _DREAM_MAP_ADVERBS,
    _DREAM_MAP_COMMON_VERBS,
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "l",
        "et",
        "ou",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "que",
        "qui",
        "quoi",
        "dont",
        "où",
        "ou",
        "ce",
        "c",
        "cet",
        "cette",
        "ces",
        "mon",
        "ton",
        "son",
        "mes",
        "tes",
        "ses",
        "nos",
        "vos",
        "leurs",
        "leur",
        "au",
        "aux",
        "pas",
        "ne",
        "rien",
        "personne",
        "tout",
        "tous",
        "toute",
        "toutes",
        "chaque",
        "aucun",
        "aucune",
        "plus",
        "moins",
    },
)


def _dream_map_split_terms(value: str) -> list[str]:
    return [term.strip("-_'’") for term in term_findall(value) if term.strip("-_'’")]


def _dream_map_is_content_word(term: str) -> bool:
    word = _normalize_tag(term)
    if not word or len(word) < 3:
        return False
    if any(ch.isdigit() for ch in word):
        return False
    if word in _DREAM_MAP_EXCLUDED_WORDS:
        return False
    if any(word.endswith(suffix) for suffix in _DREAM_MAP_VERB_SUFFIXES):
        return False
    return (
        any(word.endswith(suffix) for suffix in _DREAM_MAP_ALLOWED_SUFFIXES)
        or len(word) >= 3
    )


def _dream_map_is_keyword(value: str) -> bool:
    terms = _dream_map_split_terms(value)
    if not terms:
        return False
    return any(_dream_map_is_content_word(term) for term in terms)


def _dream_map_collect_tags(entries_dir: Path) -> list[str]:
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

    return sorted(tags)


def _ensure_semantic_store_loaded():
    global _semantic_loaded, _semantic_tag_to_group
    if _semantic_loaded:
        return
    with _semantic_lock:
        if _semantic_loaded:
            return
        if SEMANTIC_GROUPS_FILE.exists():
            try:
                with open(SEMANTIC_GROUPS_FILE) as f:
                    data = json.load(f)
                stored = data.get("tag_to_group", {}) if isinstance(data, dict) else {}
                _semantic_tag_to_group = {
                    _normalize_tag(k): str(v).strip()
                    for k, v in stored.items()
                    if _normalize_tag(k) and str(v).strip()
                }
            except Exception as e:
                log.warning(f"Failed to load semantic groups store: {e}")
                _semantic_tag_to_group = {}
        _semantic_loaded = True


def _reset_semantic_store():
    global _semantic_loaded, _semantic_tag_to_group, _semantic_pending_tags, _semantic_generation
    with _semantic_lock:
        _semantic_generation += 1
        _semantic_tag_to_group = {}
        _semantic_pending_tags = set()
        _semantic_loaded = True
    try:
        if SEMANTIC_GROUPS_FILE.exists():
            SEMANTIC_GROUPS_FILE.unlink()
    except Exception as e:
        log.warning(f"Failed to clear semantic groups store: {e}")


def _current_semantic_generation() -> int:
    with _semantic_lock:
        return int(_semantic_generation)


def _save_semantic_store():
    with _semantic_lock:
        SEMANTIC_GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "generation": _semantic_generation,
            "tag_to_group": _semantic_tag_to_group,
        }
        tmp = SEMANTIC_GROUPS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        tmp.replace(SEMANTIC_GROUPS_FILE)


def _classify_tag_with_mistral(tag: str):
    _ensure_semantic_store_loaded()
    cfg = _load_config()
    ollama_cfg = cfg.get("ollama", {})
    host = ollama_cfg.get("host", "http://127.0.0.1:11434")
    model = ollama_cfg.get("model", "mistral")
    with _semantic_lock:
        groups = sorted({v for v in _semantic_tag_to_group.values() if str(v).strip()})

    inputs = _load_mistral_inputs()
    prompt_template = inputs.get("dream_map", {}).get(
        "tag_classifier_template",
        _DEFAULT_MISTRAL_INPUTS["dream_map"]["tag_classifier_template"],
    )
    prompt = prompt_template.format(
        tag=json.dumps(tag, ensure_ascii=False),
        groups_json=json.dumps(groups, ensure_ascii=False),
    )

    try:
        import requests as req

        r = req.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 120,
                },
            },
            timeout=25,
        )
        if r.status_code != 200:
            return None
        content = (r.json().get("response") or "").strip()
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        group = str(parsed.get("group", "")).strip()
        if not group:
            return None
        return group[:48]
    except Exception as e:
        log.warning(f"Semantic tag classification failed for '{tag}': {e}")
        return None


def _classify_tag_background(tag: str, generation: int):
    try:
        if generation != _current_semantic_generation():
            return
        group = _classify_tag_with_mistral(tag)
        if group and generation == _current_semantic_generation():
            with _semantic_lock:
                _semantic_tag_to_group[tag] = group
            _save_semantic_store()
            log.info(f"Semantic group assigned: {tag} -> {group}")
        else:
            log.warning(f"No semantic group assigned yet for tag: {tag}")
    finally:
        with _semantic_lock:
            _semantic_pending_tags.discard(tag)


def _enqueue_tag_semantic_classification(tag: str, generation: int | None = None):
    t = _normalize_tag(tag)
    if not t:
        return
    _ensure_semantic_store_loaded()
    with _semantic_lock:
        if t in _semantic_tag_to_group or t in _semantic_pending_tags:
            return
        current_generation = (
            _semantic_generation if generation is None else int(generation)
        )
        _semantic_pending_tags.add(t)
    threading.Thread(
        target=_classify_tag_background, args=(t, current_generation), daemon=True
    ).start()


def _rebuild_dream_map_keywords(entries_dir: Path) -> int:
    _reset_semantic_store()
    tags = _dream_map_collect_tags(entries_dir)
    generation = _current_semantic_generation()
    for tag in tags:
        _enqueue_tag_semantic_classification(tag, generation=generation)
    return len(tags)


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    config = _load_config()
    return {
        "status": "ok",
        "sandman": "ready",
        "transcribing": transcriber.is_active,
        "correcting": corrector.is_active,
        "correction_enabled": config.get("correction", {}).get("enabled", False),
    }


@app.post("/upload")
async def upload(
    audio: UploadFile = File(...),
    timestamp: str = Form(...),
    duration_seconds: int = Form(0),
    dream_date: str = Form(None),
    x_api_key: str = Header(None),
):
    _verify_api_key(x_api_key)

    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp
    entry_dir.mkdir(parents=True, exist_ok=True)

    # Save audio file preserving original extension
    ext = (
        "webm"
        if audio.filename.endswith(".webm")
        else "mp4" if audio.filename.endswith(".mp4") else "wav"
    )
    audio_path = entry_dir / f"audio.{ext}"
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    meta = {
        "timestamp": timestamp,
        "dream_date": _normalize_dream_date(dream_date),
        "received_at": datetime.now().isoformat(),
        "duration_seconds": duration_seconds,
        "transcribed": False,
        "corrected": False,
        "notified": False,
        "sent": False,
    }
    with open(entry_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    threading.Thread(target=transcriber.enqueue, args=[entry_dir], daemon=True).start()

    log.info(f"Received upload: {timestamp} ({duration_seconds}s)")
    return JSONResponse({"status": "ok", "entry": timestamp})


@app.post("/entries/manual")
async def create_manual_entry(request: Request, x_api_key: str = Header(None)):
    """Create a manual text entry directly from the PWA."""
    _verify_api_key(x_api_key)
    body = await request.json()
    text = body.get("text", "").strip()
    dream_date = _normalize_dream_date(body.get("dream_date"))
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    entry_dir = entries_dir / timestamp
    entry_dir.mkdir(parents=True, exist_ok=True)

    (entry_dir / "transcript_raw.txt").write_text(text)
    (entry_dir / "transcript_corrected.txt").write_text(text)

    meta = {
        "timestamp": timestamp,
        "dream_date": dream_date,
        "received_at": datetime.now().isoformat(),
        "duration_seconds": 0,
        "source": "manual",
        "transcribed": True,
        "corrected": True,
        "notified": False,
        "sent": False,
    }
    with open(entry_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    log.info(f"Manual entry created: {timestamp}")
    return JSONResponse({"status": "ok", "entry": timestamp})


@app.get("/entries")
def list_entries(x_api_key: str = Header(None)):
    """List all entries with their metadata and transcript preview."""
    _cleanup_stale_interpretations()
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entries = []
    if entries_dir.exists():
        for entry in sorted(entries_dir.iterdir(), reverse=True):
            if not entry.is_dir():
                continue
            meta_file = entry / "meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    meta = json.load(f)

                _apply_dream_date_fallback(meta)

                # Surface interpretation background activity at entry level.
                ts = meta.get("timestamp", entry.name)
                prefix = f"{ts}_"
                meta["interpretation_pending"] = any(
                    job_key.startswith(prefix)
                    for job_key in _interpretation_queue.keys()
                )

                # Add transcript preview — prefer user > corrected > raw
                user = entry / "transcript_user.txt"
                corrected = entry / "transcript_corrected.txt"
                raw = entry / "transcript_raw.txt"
                if user.exists():
                    meta["transcript_preview"] = user.read_text()[:150]
                elif corrected.exists():
                    meta["transcript_preview"] = corrected.read_text()[:150]
                elif raw.exists():
                    meta["transcript_preview"] = raw.read_text()[:150]
                entries.append(meta)
    return JSONResponse(entries)


@app.get("/entries/{timestamp}")
def get_entry(timestamp: str, x_api_key: str = Header(None)):
    """Get a single entry with all its transcripts."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    meta_file = entry_dir / "meta.json"
    meta = {}
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)

    _apply_dream_date_fallback(meta)

    raw_file = entry_dir / "transcript_raw.txt"
    if raw_file.exists():
        meta["transcript_raw"] = raw_file.read_text()

    corrected_file = entry_dir / "transcript_corrected.txt"
    if corrected_file.exists():
        meta["transcript_corrected"] = corrected_file.read_text()

    user_file = entry_dir / "transcript_user.txt"
    if user_file.exists():
        meta["transcript_user"] = user_file.read_text()

    return JSONResponse(meta)


@app.get("/entries/{timestamp}/audio")
def get_audio(timestamp: str, x_api_key: str = Header(None)):
    """Stream the audio file for an entry."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    audio = next(entry_dir.glob("audio.*"), None)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(str(audio))


@app.post("/entries/{timestamp}/correct")
def correct_entry(timestamp: str, x_api_key: str = Header(None)):
    """Manually trigger LLM correction for a specific entry."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    meta_file = entry_dir / "meta.json"
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)
        meta["corrected"] = False
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

    corrector.enqueue(entry_dir)
    return JSONResponse(
        {"status": "ok", "message": f"Correction queued for {timestamp}"}
    )


@app.post("/entries/{timestamp}/tags")
async def update_tags(timestamp: str, request: Request, x_api_key: str = Header(None)):
    """Update tags for an entry. Body: {\"tags\": [\"lucide\", \"cauchemar\"]}"""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    tags = body.get("tags", [])

    meta_file = entry_dir / "meta.json"
    with open(meta_file) as f:
        meta = json.load(f)
    meta["tags"] = tags
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    # Classify newly added tags in background for Dream Map semantic grouping.
    for tag in tags:
        _enqueue_tag_semantic_classification(tag)

    log.info(f"Tags updated for {timestamp}: {tags}")
    return JSONResponse({"status": "ok"})


@app.post("/entries/{timestamp}/save-transcript")
async def save_transcript(
    timestamp: str, request: Request, x_api_key: str = Header(None)
):
    """Save user-edited transcript. Body: {\"text\": \"...\"}"""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    (entry_dir / "transcript_user.txt").write_text(text)
    log.info(f"User transcript saved: {timestamp}")
    return JSONResponse({"status": "ok"})


@app.post("/entries/{timestamp}/dream-date")
async def update_dream_date(
    timestamp: str, request: Request, x_api_key: str = Header(None)
):
    """Update dream_date for an existing entry. Body: {"dream_date": "ISO-8601"}"""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    dream_date = _normalize_dream_date(body.get("dream_date"))
    if dream_date is None:
        raise HTTPException(status_code=400, detail="dream_date is required")

    meta_file = entry_dir / "meta.json"
    meta = {}
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)

    meta["dream_date"] = dream_date

    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    log.info(f"Dream date updated for {timestamp}: {dream_date}")
    return JSONResponse({"status": "ok", "dream_date": dream_date})


@app.delete("/entries/{timestamp}")
def delete_entry(timestamp: str, x_api_key: str = Header(None)):
    """Delete an entry and all its files."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    shutil.rmtree(entry_dir)
    log.info(f"Deleted entry: {timestamp}")
    return JSONResponse({"status": "ok"})


INTERPRETERS = {
    "fool": {
        "name": "Le Fou",
        "prompt": """Tu es Le Fou, interprète de rêves facétieux inspiré du fou du roi. Donne une lecture symbolique et psychologique SANS résumer le récit ni répéter les scènes. Structure: 1) tension intérieure probable, 2) angle absurde éclairant, 3) mini-conseil concret pour demain. 3 phrases maximum. Pas d'introduction.\n\nRêve: {text}""",
    },
    "freud": {
        "name": "Sigmund",
        "prompt": """Tu es Sigmund, interprète de rêves analytique inspiré de Freud. Analyse SANS paraphraser le rêve: identifie le conflit psychique central, le désir/peur sous-jacent, puis une hypothèse de mécanisme (défense, déplacement, etc.). 3 phrases maximum. Pas d'introduction.\n\nRêve: {text}""",
    },
    "cassandra": {
        "name": "Cassandre",
        "prompt": """Tu es Cassandre, prophétesse mystique. Interprète les symboles en profondeur SANS raconter le rêve. Donne: 1) symbole maître, 2) mouvement intérieur qu'il annonce, 3) geste rituel simple pour intégrer le message. 3 phrases maximum, poétiques mais claires, sans introduction.\n\nRêve: {text}""",
    },
    "oracle": {
        "name": "L'Oracle",
        "prompt": """Tu es un oracle bienveillant. Interprète ce rêve SANS le reformuler: cible le besoin émotionnel principal, l'élan de transformation, et un conseil actionnable pour la journée. 3 phrases maximum. Ton chaleureux, pas d'introduction.\n\nRêve: {text}""",
    },
}


def _interpreter_prompt(interpreter_key: str, text: str) -> str:
    inputs = _load_mistral_inputs()
    profile = _user_profile_for_prompt()
    addressing = _user_addressing_instruction()
    return build_interpreter_prompt(
        interpreter_key,
        text,
        inputs,
        INTERPRETERS[interpreter_key]["prompt"],
        profile,
        addressing,
        profile_block_label="Contexte utilisateur (a prendre en compte dans l'interpretation):",
        addressing_block_label="Consigne d'adresse prioritaire:",
    )


def _interpretation_prompt_signature(interpreter_key: str) -> str:
    inputs = _load_mistral_inputs()
    return interpreter_prompt_signature(
        interpreter_key,
        inputs,
        builder_version="2026-04-25-pronouns-v2",
        user_profile_sig=_user_profile_signature(),
        fallback_prompts={
            interpreter_key: INTERPRETERS[interpreter_key]["prompt"],
            "compact": _DEFAULT_MISTRAL_INPUTS["interpretation"]["compact_template"],
            "anti": _DEFAULT_MISTRAL_INPUTS["interpretation"]["anti_paraphrase_template"],
        },
    )


# Track in-progress interpretations
_interpretation_queue = {}
_interpretation_errors = {}
_interpretation_job_tokens = {}


def _cleanup_stale_interpretations():
    """Expire stuck interpretation jobs and surface a clear error state."""
    config = _load_config()
    interp_cfg = config.get("interpretation", {})
    max_pending = int(interp_cfg.get("max_pending_seconds", 180))
    if max_pending <= 0:
        return
    now = time.time()

    stale_jobs = [
        key
        for key, started_at in _interpretation_queue.items()
        if (now - started_at) > max_pending
    ]
    for key in stale_jobs:
        _interpretation_queue.pop(key, None)
        _interpretation_errors[key] = f"Timed out after {max_pending}s"
        log.error(f"Interpretation job expired: {key} (>{max_pending}s)")


def _is_digest_job_current(job_key: str, token: int) -> bool:
    return int(_digest_job_tokens.get(job_key, 0)) == int(token)


def _is_interpretation_job_current(job_key: str, token: int) -> bool:
    return int(_interpretation_job_tokens.get(job_key, 0)) == int(token)


def _compact_interpret_prompt(interpreter_name: str, text: str) -> str:
    inputs = _load_mistral_inputs()
    profile = _user_profile_for_prompt()
    addressing = _user_addressing_instruction()
    return compact_interpret_prompt(
        interpreter_name,
        text,
        inputs,
        profile,
        addressing,
        profile_block_label="Contexte utilisateur:",
        addressing_block_label="Consigne d'adresse prioritaire:",
    )


def _anti_paraphrase_prompt(interpreter_name: str, text: str) -> str:
    inputs = _load_mistral_inputs()
    profile = _user_profile_for_prompt()
    addressing = _user_addressing_instruction()
    return anti_paraphrase_prompt(
        interpreter_name,
        text,
        inputs,
        profile,
        addressing,
        profile_block_label="Contexte utilisateur:",
        addressing_block_label="Consigne d'adresse prioritaire:",
    )


def _word_overlap_ratio(source: str, candidate: str) -> float:
    return word_overlap_ratio(source, candidate)


def _local_interpretation_fallback(interpreter_key: str, text: str) -> str:
    return local_interpretation_fallback(interpreter_key, text)


@app.post("/entries/{timestamp}/interpret")
async def interpret_entry(
    timestamp: str, request: Request, x_api_key: str = Header(None)
):
    """Generate a dream interpretation in the background.

    Request body:
    - interpreter: one of INTERPRETERS keys (default: oracle)
    - force: optional bool-like flag to ignore/delete cached interpretation file
    """
    _cleanup_stale_interpretations()
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    interpreter_key = body.get("interpreter", "oracle")
    force_raw = body.get("force", False)
    force = (
        str(force_raw).strip().lower() in {"1", "true", "yes", "on"}
        if not isinstance(force_raw, bool)
        else force_raw
    )

    if interpreter_key not in INTERPRETERS:
        raise HTTPException(status_code=400, detail="Invalid interpreter")

    # Return cached result immediately unless forced.
    interp_file = entry_dir / f"interpretation_{interpreter_key}.txt"
    interp_meta_file = _interpretation_meta_path(entry_dir, interpreter_key)
    current_prompt_signature = _interpretation_prompt_signature(interpreter_key)
    job_key = f"{timestamp}_{interpreter_key}"
    if force:
        _interpretation_job_tokens[job_key] = (
            int(_interpretation_job_tokens.get(job_key, 0)) + 1
        )
        _interpretation_queue.pop(job_key, None)
        _interpretation_errors.pop(job_key, None)

    worker_token = int(_interpretation_job_tokens.get(job_key, 0))
    if force and interp_file.exists():
        try:
            interp_file.unlink()
            if interp_meta_file.exists():
                interp_meta_file.unlink()
            log.info(
                f"Interpretation cache removed (force): {timestamp} / {interpreter_key}"
            )
        except Exception as e:
            log.warning(f"Failed to remove interpretation cache (force): {e}")

    if interp_file.exists():
        meta = _read_interpretation_meta(entry_dir, interpreter_key)
        cached_signature = meta.get("prompt_signature")
        if cached_signature != current_prompt_signature:
            try:
                interp_file.unlink()
                if interp_meta_file.exists():
                    interp_meta_file.unlink()
                log.info(
                    f"Interpretation cache invalidated (prompt change): {timestamp} / {interpreter_key}"
                )
            except Exception as e:
                log.warning(
                    f"Failed to invalidate interpretation cache after prompt change: {e}"
                )
        else:
            _interpretation_errors.pop(job_key, None)
            return JSONResponse(
                {
                    "status": "ok",
                    "interpreter": INTERPRETERS[interpreter_key]["name"],
                    "interpretation": interp_file.read_text(),
                    "source": meta.get("source") or "mistral",
                    "generation_seconds": meta.get("generation_seconds"),
                }
            )

    if interp_file.exists():
        _interpretation_errors.pop(job_key, None)
        meta = _read_interpretation_meta(entry_dir, interpreter_key)
        return JSONResponse(
            {
                "status": "ok",
                "interpreter": INTERPRETERS[interpreter_key]["name"],
                "interpretation": interp_file.read_text(),
                "source": meta.get("source") or "mistral",
                "generation_seconds": meta.get("generation_seconds"),
            }
        )

    # Already in progress
    if job_key in _interpretation_queue:
        return JSONResponse({"status": "pending", "forced": bool(force)})

    # Get transcript
    text = ""
    for fname in [
        "transcript_user.txt",
        "transcript_corrected.txt",
        "transcript_raw.txt",
    ]:
        f = entry_dir / fname
        if f.exists():
            text = f.read_text().strip()
            break

    if not text:
        raise HTTPException(status_code=400, detail="No transcript available")

    # Launch in background thread
    _interpretation_queue[job_key] = time.time()
    _interpretation_errors.pop(job_key, None)

    def run_interpretation():
        # Delegate the heavy lifting to the interpretation module's job runner.
        try:
            success, error = run_interpretation_job(
                entry_dir=entry_dir,
                timestamp=timestamp,
                interpreter_key=interpreter_key,
                text=text,
                job_key=job_key,
                worker_token=worker_token,
                current_prompt_signature=current_prompt_signature,
                load_config_fn=_load_config,
                is_job_current_fn=_is_interpretation_job_current,
                write_interpretation_fn=_write_interpretation,
                normalize_timeout_fn=_normalize_timeout_seconds,
            )
            if success:
                _interpretation_errors.pop(job_key, None)
                log.info(
                    f"Interpretation ({interpreter_key}) done: {timestamp} via job runner"
                )
            else:
                if error and _is_interpretation_job_current(job_key, worker_token):
                    _interpretation_errors[job_key] = error
        except Exception as e:
            if _is_interpretation_job_current(job_key, worker_token):
                _interpretation_errors[job_key] = str(e)
            log.error(f"Interpretation failed: {e}")
        finally:
            if _is_interpretation_job_current(job_key, worker_token):
                _interpretation_queue.pop(job_key, None)

    threading.Thread(target=run_interpretation, daemon=True).start()
    return JSONResponse({"status": "pending", "forced": bool(force)})


@app.get("/entries/{timestamp}/interpretations")
def get_interpretations(timestamp: str, x_api_key: str = Header(None)):
    """Get all existing interpretations for an entry."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    result = {}
    for key, interp in INTERPRETERS.items():
        f = entry_dir / f"interpretation_{key}.txt"
        if f.exists():
            meta = _read_interpretation_meta(entry_dir, key)
            result[key] = {
                "name": interp["name"],
                "text": f.read_text(),
                "source": meta.get("source") or "mistral",
                "generation_seconds": meta.get("generation_seconds"),
            }

    return JSONResponse(result)


@app.get("/entries/{timestamp}/interpret-status")
def get_interpret_status(timestamp: str, x_api_key: str = Header(None)):
    """Get interpretation status per interpreter: done/pending/error."""
    _cleanup_stale_interpretations()
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    status = {}
    for key in INTERPRETERS.keys():
        job_key = f"{timestamp}_{key}"
        interp_file = entry_dir / f"interpretation_{key}.txt"
        done = interp_file.exists()
        started_at = float(_interpretation_queue.get(job_key) or 0)
        is_pending = job_key in _interpretation_queue
        if done:
            _interpretation_errors.pop(job_key, None)

        status[key] = {
            "done": done,
            "pending": is_pending,
            "error": _interpretation_errors.get(job_key),
            "pending_seconds": (
                round(max(0.0, time.time() - started_at), 1)
                if is_pending and started_at > 0
                else None
            ),
        }

    return JSONResponse(status)


@app.post("/entries/{timestamp}/interpret/cancel")
async def cancel_interpretation(
    timestamp: str, request: Request, x_api_key: str = Header(None)
):
    """Cancel one (or all) in-flight interpretation jobs for an entry."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = entries_dir / timestamp
    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json() if request else {}
    interpreter_key = (body or {}).get("interpreter")
    if interpreter_key and interpreter_key not in INTERPRETERS:
        raise HTTPException(status_code=400, detail="Invalid interpreter")

    keys = [interpreter_key] if interpreter_key else list(INTERPRETERS.keys())
    canceled = []
    for key in keys:
        job_key = f"{timestamp}_{key}"
        _interpretation_job_tokens[job_key] = (
            int(_interpretation_job_tokens.get(job_key, 0)) + 1
        )
        was_pending = job_key in _interpretation_queue
        _interpretation_queue.pop(job_key, None)
        _interpretation_errors.pop(job_key, None)
        if was_pending:
            canceled.append(key)

    return JSONResponse(
        {
            "status": "ok",
            "timestamp": timestamp,
            "canceled": canceled,
            "requested": keys,
        }
    )


def _fallback_semantic_cluster(label: str):
    label_l = (label or "").lower()
    if any(
        k in label_l
        for k in [
            "peur",
            "angoisse",
            "cauchemar",
            "nuit",
            "ombre",
            "poursuite",
            "stress",
            "panique",
        ]
    ):
        return "Tensions"
    if any(
        k in label_l
        for k in ["train", "gare", "pont", "velo", "route", "voyage", "tunnel", "ville"]
    ):
        return "Mouvements"
    if any(
        k in label_l
        for k in [
            "eau",
            "ocean",
            "pluie",
            "neige",
            "foret",
            "fleurs",
            "lavande",
            "desert",
            "renard",
        ]
    ):
        return "Nature"
    if any(
        k in label_l
        for k in [
            "maison",
            "lit",
            "porte",
            "miroir",
            "cle",
            "cinema",
            "ecole",
            "hopital",
            "bibliotheque",
        ]
    ):
        return "Lieux"
    if any(
        k in label_l
        for k in ["famille", "amis", "enfance", "grand", "chien", "personnes"]
    ):
        return "Relations"
    if any(
        k in label_l
        for k in [
            "temps",
            "memoire",
            "futur",
            "message",
            "intuition",
            "identite",
            "secret",
        ]
    ):
        return "Symboles"
    return "Mots"


@app.get("/dream-map")
def get_dream_map(x_api_key: str = Header(None)):
    """Return dream-map nodes and semantic groups for visualization.

    Tag grouping is resolved incrementally in background when new tags are added.
    Unresolved tags remain ungrouped and are marked as pending while classification runs.
    """
    _verify_api_key(x_api_key)
    _ensure_semantic_store_loaded()
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])

    if not entries_dir.exists():
        return JSONResponse({"nodes": [], "groups": []})

    tag_counts = {}
    word_counts = {}

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
            tag = _normalize_tag(tag)
            if tag and _dream_map_is_keyword(tag):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        text = ""
        for fname in [
            "transcript_user.txt",
            "transcript_corrected.txt",
            "transcript_raw.txt",
        ]:
            f = entry / fname
            if f.exists():
                text = f.read_text().strip().lower()
                break

        if text:
            tokens = _TOKEN_RE.findall(text)
            for tok in tokens:
                t = tok.strip("-'’")
                if t.startswith(("d'", "l'", "j'", "qu'", "d’", "l’", "j’", "qu’")):
                    t = t.split("'", 1)[-1] if "'" in t else t.split("’", 1)[-1]
                t = t.strip("-'’")
                if _dream_map_is_content_word(t):
                    word_counts[t] = word_counts.get(t, 0) + 1

    with _semantic_lock:
        cache_snapshot = dict(_semantic_tag_to_group)
        pending_snapshot = set(_semantic_pending_tags)

    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
    selected_tags = []
    selected_set = set()

    # Main signal: dominant tags.
    for tag, count in sorted_tags[:18]:
        selected_tags.append((tag, count))
        selected_set.add(tag)

    # Always include tags currently being semantically classified.
    for tag in pending_snapshot:
        if tag in tag_counts and tag not in selected_set:
            selected_tags.append((tag, tag_counts[tag]))
            selected_set.add(tag)

    # Keep ungrouped tags visible so user can see them outside groups.
    for tag, count in sorted_tags:
        if tag in selected_set:
            continue
        if tag not in cache_snapshot:
            selected_tags.append((tag, count))
            selected_set.add(tag)
        if len(selected_tags) >= 28:
            break

    tag_nodes = [{"label": k, "value": v, "kind": "tag"} for k, v in selected_tags]
    word_nodes = [
        {
            "label": k,
            "value": v,
            "kind": "word",
            "cluster": _fallback_semantic_cluster(k),
            "pending": False,
        }
        for k, v in sorted(word_counts.items(), key=lambda x: -x[1])[:24]
    ]
    nodes = []

    with _semantic_lock:
        cache = dict(_semantic_tag_to_group)
        pending = set(_semantic_pending_tags)

    for n in tag_nodes:
        label = _normalize_tag(n["label"])
        cluster = cache.get(label)
        is_pending = label in pending
        nodes.append(
            {
                **n,
                "cluster": cluster,
                "pending": is_pending,
            }
        )

    nodes.extend(word_nodes)

    if not nodes:
        return JSONResponse({"nodes": [], "groups": []})

    group_counts = {}
    for n in nodes:
        c = n["cluster"]
        if not c:
            continue
        group_counts[c] = group_counts.get(c, 0) + 1

    groups = [
        {"name": k, "count": v}
        for k, v in sorted(group_counts.items(), key=lambda x: -x[1])
    ]

    return JSONResponse({"nodes": nodes, "groups": groups})


@app.post("/dream-map/reset")
def reset_dream_map(x_api_key: str = Header(None)):
    """Clear semantic group cache and re-sort all tracked Dream Map keywords."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])

    if not entries_dir.exists():
        _reset_semantic_store()
        return JSONResponse({"status": "ok", "queued": 0})

    queued = _rebuild_dream_map_keywords(entries_dir)
    return JSONResponse({"status": "ok", "queued": queued})


@app.get("/stats")
def get_stats(x_api_key: str = Header(None)):
    """Compute statistics across all entries."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])

    if not entries_dir.exists():
        return JSONResponse({})

    # French stopwords
    STOPWORDS = {
        "je",
        "tu",
        "il",
        "elle",
        "nous",
        "vous",
        "ils",
        "elles",
        "me",
        "te",
        "se",
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "l",
        "y",
        "en",
        "et",
        "est",
        "était",
        "être",
        "avoir",
        "que",
        "qui",
        "quoi",
        "dont",
        "où",
        "ou",
        "et",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "si",
        "plus",
        "très",
        "bien",
        "tout",
        "tous",
        "cette",
        "ce",
        "cet",
        "ces",
        "mon",
        "ton",
        "son",
        "ma",
        "ta",
        "sa",
        "nos",
        "vos",
        "leurs",
        "leur",
        "au",
        "aux",
        "par",
        "pour",
        "sur",
        "sous",
        "dans",
        "avec",
        "sans",
        "entre",
        "vers",
        "chez",
        "après",
        "avant",
        "pendant",
        "alors",
        "puis",
        "aussi",
        "même",
        "comme",
        "quand",
        "car",
        "encore",
        "déjà",
        "jamais",
        "toujours",
        "pas",
        "ne",
        "plus",
        "rien",
        "personne",
        "non",
        "oui",
        "ah",
        "oh",
        "a",
        "à",
        "ça",
        "là",
        "lui",
        "eux",
        "on",
        "j",
        "m",
        "t",
        "s",
        "c",
        "n",
        "qu",
        "j'ai",
        "j'étais",
        "c'est",
        "c'était",
        "il",
        "avait",
        "était",
        "fait",
        "faire",
        "aller",
        "venir",
        "voir",
        "savoir",
        "pouvoir",
        "vouloir",
        "falloir",
        "avoir",
        "être",
        "dit",
        "allait",
        "venait",
        "ai",
        "as",
        "ont",
        "une",
        "the",
        "and",
        "but",
        "with",
        "from",
        "this",
        "that",
        "they",
        "them",
        "their",
    }

    # Normalize French elisions so stats don't surface fragments like "avais" from "j'avais".
    elision_prefixes = (
        "d'",
        "l'",
        "j'",
        "t'",
        "m'",
        "n'",
        "s'",
        "c'",
        "qu'",
        "puisqu'",
        "lorsqu'",
        "d’",
        "l’",
        "j’",
        "t’",
        "m’",
        "n’",
        "s’",
        "c’",
        "qu’",
        "puisqu’",
        "lorsqu’",
    )

    def _stats_tokens(text: str):
        tokens = re.findall(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ'’\-]{2,}", (text or "").lower())
        normalized = []
        for token in tokens:
            t = token.strip("-'’")
            for prefix in elision_prefixes:
                if t.startswith(prefix):
                    t = t[len(prefix) :]
                    break
            t = t.strip("-'’")
            if len(t) >= 4 and t not in STOPWORDS:
                normalized.append(t)
        return normalized

    entries = []
    all_words = []
    tag_counts = {}
    tag_counts_30 = {}
    total_chars = 0
    monthly = {}
    from datetime import datetime, timedelta

    now = datetime.now()
    cutoff_30 = now - timedelta(days=30)

    for entry in entries_dir.iterdir():
        if not entry.is_dir():
            continue
        meta_file = entry / "meta.json"
        if not meta_file.exists():
            continue
        with open(meta_file) as f:
            meta = json.load(f)

        if not meta.get("transcribed"):
            continue

        entries.append(meta)

        # Parse date
        try:
            ts = meta.get("timestamp", "")
            date_str = ts.split("_")[0]
            entry_date = datetime.strptime(date_str, "%Y-%m-%d")
            month_key = entry_date.strftime("%Y-%m")
            monthly[month_key] = monthly.get(month_key, 0) + 1
            is_recent = entry_date >= cutoff_30
        except Exception:
            is_recent = False
            month_key = None

        # Transcript length
        for fname in [
            "transcript_user.txt",
            "transcript_corrected.txt",
            "transcript_raw.txt",
        ]:
            f = entry / fname
            if f.exists():
                text = f.read_text().strip()
                total_chars += len(text)

                # Word frequency — robust French tokenization with apostrophe handling.
                all_words.extend(_stats_tokens(text))
                break

        # Tags
        for tag in meta.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if is_recent:
                tag_counts_30[tag] = tag_counts_30.get(tag, 0) + 1

    total = len(entries)
    avg_length = round(total_chars / total) if total > 0 else 0

    # Top words
    from collections import Counter

    word_freq = Counter(all_words).most_common(30)

    # Monthly sorted
    sorted_monthly = dict(sorted(monthly.items()))
    months_list = list(sorted_monthly.items())[-12:]  # last 12 months

    avg_per_month = round(total / max(len(sorted_monthly), 1), 1) if total > 0 else 0

    return JSONResponse(
        {
            "total_entries": total,
            "avg_length": avg_length,
            "avg_per_month": avg_per_month,
            "top_tags": sorted(tag_counts.items(), key=lambda x: -x[1])[:15],
            "top_tags_30": sorted(tag_counts_30.items(), key=lambda x: -x[1])[:10],
            "top_words": word_freq,
            "monthly": months_list,
        }
    )


@app.get("/digest/weekly")
def weekly_digest(days: int = 7, weeks_ago: int = 0, x_api_key: str = Header(None)):
    """Return a compact weekly digest of recent dreams for the PWA."""
    _verify_api_key(x_api_key)
    return JSONResponse(_compute_weekly_digest_payload(days, weeks_ago))


def _compute_weekly_digest_payload(days: int = 7, weeks_ago: int = 0):
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])

    if not entries_dir.exists():
        return {"days": days, "entries": []}

    from datetime import timedelta
    import calendar
    from collections import Counter

    days = 7
    weeks_ago = max(0, min(int(weeks_ago or 0), 26))
    now = datetime.now()
    today = now.date()

    # Fixed weekly window: Monday -> Sunday.
    current_monday = today - timedelta(days=today.weekday())
    week_start_date = current_monday - timedelta(days=weeks_ago * 7)
    week_end_date = week_start_date + timedelta(days=6)
    week_complete = week_end_date < today

    # window_start/window_end intentionally unused; remove to satisfy linters.

    stopwords = {
        "je",
        "tu",
        "il",
        "elle",
        "nous",
        "vous",
        "ils",
        "elles",
        "me",
        "te",
        "se",
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "l",
        "y",
        "en",
        "et",
        "est",
        "etait",
        "etre",
        "avoir",
        "que",
        "qui",
        "quoi",
        "dont",
        "ou",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "si",
        "plus",
        "tres",
        "bien",
        "tout",
        "tous",
        "cette",
        "ce",
        "cet",
        "ces",
        "mon",
        "ton",
        "son",
        "ma",
        "ta",
        "sa",
        "nos",
        "vos",
        "leurs",
        "leur",
        "au",
        "aux",
        "par",
        "pour",
        "sur",
        "sous",
        "dans",
        "avec",
        "sans",
        "entre",
        "vers",
        "chez",
        "apres",
        "avant",
        "pendant",
        "alors",
        "puis",
        "aussi",
        "meme",
        "comme",
        "quand",
        "encore",
        "deja",
        "jamais",
        "toujours",
        "pas",
        "ne",
        "rien",
        "personne",
        "non",
        "oui",
        "suis",
        "etais",
        "étais",
        "etaient",
        "étaient",
        "avais",
        "avait",
        "avions",
        "aviez",
        "ont",
        "etre",
    }

    nightmare_terms = {
        "cauchemar",
        "peur",
        "angoisse",
        "panique",
        "sombre",
        "cri",
        "poursuite",
        "tomber",
    }

    def _safe_parse_dt(meta):
        for key in ["dream_date", "received_at"]:
            raw = meta.get(key)
            if raw:
                try:
                    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone().replace(tzinfo=None)
                    return dt
                except Exception:
                    pass
        ts = meta.get("timestamp", "")
        try:
            return datetime.strptime(ts.split("_")[0], "%Y-%m-%d")
        except Exception:
            return None

    entries = []
    tag_counter = Counter()
    word_counter = Counter()
    nightmare_count = 0
    daily_counter = Counter()

    month_ref = datetime.combine(week_end_date, datetime.min.time())
    cal_year = month_ref.year
    cal_month = month_ref.month
    month_start = datetime(cal_year, cal_month, 1)
    month_days = calendar.monthrange(cal_year, cal_month)[1]
    month_end = datetime(cal_year, cal_month, month_days, 23, 59, 59)
    month_night_counter = Counter()

    for entry in sorted(entries_dir.iterdir(), reverse=True):
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

        if not meta.get("transcribed"):
            continue

        dt = _safe_parse_dt(meta)
        if not dt:
            continue
        day_only = dt.date()
        if day_only < week_start_date or day_only > week_end_date:
            continue

        text = ""
        for fname in [
            "transcript_user.txt",
            "transcript_corrected.txt",
            "transcript_raw.txt",
        ]:
            f = entry / fname
            if f.exists():
                text = f.read_text().strip()
                break

        tags = [
            str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()
        ]
        tag_counter.update(tags)

        lowered = text.lower()
        tokens = re.findall(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ'’\-]{3,}", lowered)
        cleaned = []
        for tok in tokens:
            t = tok.strip("-'’")
            if t.startswith(("d'", "l'", "j'", "qu'", "d’", "l’", "j’", "qu’")):
                t = t.split("'", 1)[-1] if "'" in t else t.split("’", 1)[-1]
            t = t.strip("-'’")
            if len(t) >= 4 and t not in stopwords:
                cleaned.append(t)
        word_counter.update(cleaned)

        is_nightmare = bool(nightmare_terms.intersection(set(tags))) or any(
            term in lowered for term in nightmare_terms
        )
        if is_nightmare:
            nightmare_count += 1

        day_key = dt.strftime("%Y-%m-%d")
        daily_counter[day_key] += 1

        if month_start <= dt <= month_end:
            month_night_counter[dt.day] += 1

        entries.append(
            {
                "timestamp": meta.get("timestamp", entry.name),
                "dream_date": meta.get("dream_date") or meta.get("received_at"),
                "preview": (text[:170] + "…") if len(text) > 170 else text,
                "tags": tags[:6],
                "nightmare": is_nightmare,
            }
        )

    total_entries = len(entries)
    ratio = (nightmare_count / total_entries) if total_entries else 0.0
    tension_level = "high" if ratio >= 0.45 else "medium" if ratio >= 0.2 else "low"

    # Keep day buckets stable in order.
    daily = []
    for i in range(7):
        d = (week_start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        daily.append({"date": d, "count": daily_counter.get(d, 0)})

    return {
        "days": 7,
        "weeks_ago": weeks_ago,
        "window_start": week_start_date.strftime("%Y-%m-%d"),
        "window_end": week_end_date.strftime("%Y-%m-%d"),
        "week_complete": week_complete,
        "calendar": {
            "year": cal_year,
            "month": cal_month,
            "first_weekday": month_start.weekday(),
            "days_in_month": month_days,
            "dream_nights": [
                {"day": day, "count": count}
                for day, count in sorted(month_night_counter.items())
            ],
        },
        "total_entries": total_entries,
        "nightmare_entries": nightmare_count,
        "nightmare_ratio": round(ratio, 2),
        "tension_level": tension_level,
        "top_tags": tag_counter.most_common(10),
        "top_words": word_counter.most_common(12),
        "daily": daily,
        "highlights": entries[:8],
    }


def _fallback_digest_summary(payload: dict) -> str:
    total = int(payload.get("total_entries") or 0)
    nightmares = int(payload.get("nightmare_entries") or 0)
    tension = payload.get("tension_level") or "low"
    top_tags = [t for t, _ in (payload.get("top_tags") or [])[:3]]
    top_words = [w for w, _ in (payload.get("top_words") or [])[:4]]

    if total == 0:
        return "Peu de donnees cette semaine: aucun reve transcrit sur la periode. Relance le digest apres de nouvelles entrees pour obtenir une synthese utile."

    return (
        f"Sur les {payload.get('days', 7)} derniers jours, {total} reves ont ete enregistres, dont {nightmares} a tonalite cauchemardesque. "
        f"Le niveau global de tension ressort comme {tension}. "
        f"Les themes qui reviennent le plus sont: {', '.join(top_tags) if top_tags else 'aucun tag dominant net'}. "
        f"Le vocabulaire recurrent met en avant: {', '.join(top_words) if top_words else 'peu de mots dominants'}. "
        "Piste utile: note au reveil un mot-emotion principal pour comparer son evolution sur les prochains jours."
    )


def _compact_digest_for_prompt(payload: dict) -> dict:
    """Reduce prompt size to improve Ollama response latency/reliability."""
    highlights = payload.get("highlights") or []
    compact_highlights = []
    for h in highlights[:4]:
        compact_highlights.append(
            {
                "date": h.get("dream_date") or h.get("timestamp"),
                "nightmare": bool(h.get("nightmare")),
                "tags": (h.get("tags") or [])[:4],
                "preview": str(h.get("preview") or "")[:110],
            }
        )

    return {
        "days": payload.get("days"),
        "weeks_ago": payload.get("weeks_ago"),
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "total_entries": payload.get("total_entries"),
        "nightmare_entries": payload.get("nightmare_entries"),
        "nightmare_ratio": payload.get("nightmare_ratio"),
        "tension_level": payload.get("tension_level"),
        "top_tags": (payload.get("top_tags") or [])[:8],
        "top_words": (payload.get("top_words") or [])[:10],
        "daily": payload.get("daily") or [],
        "highlights": compact_highlights,
    }


def _digest_brief_for_prompt(payload: dict) -> str:
    """Build a compact textual brief for local CPU LLMs."""
    top_tags = (
        ", ".join([str(t) for t, _ in (payload.get("top_tags") or [])[:6]]) or "none"
    )
    top_words = (
        ", ".join([str(w) for w, _ in (payload.get("top_words") or [])[:8]]) or "none"
    )
    highlights = payload.get("highlights") or []
    highlight_lines = []
    for h in highlights[:3]:
        date = h.get("dream_date") or h.get("timestamp") or "unknown-date"
        tags = ", ".join((h.get("tags") or [])[:3])
        prev = str(h.get("preview") or "").replace("\n", " ").strip()[:90]
        nightmare = "yes" if h.get("nightmare") else "no"
        highlight_lines.append(
            f"- {date} | nightmare={nightmare} | tags={tags or 'none'} | {prev}"
        )

    lines = [
        f"window: {payload.get('window_start')} -> {payload.get('window_end')}",
        f"days: {payload.get('days')}",
        f"total_entries: {payload.get('total_entries')}",
        f"nightmare_entries: {payload.get('nightmare_entries')}",
        f"nightmare_ratio: {payload.get('nightmare_ratio')}",
        f"tension_level: {payload.get('tension_level')}",
        f"top_tags: {top_tags}",
        f"top_words: {top_words}",
        "highlights:",
        *(highlight_lines if highlight_lines else ["- none"]),
    ]
    return "\n".join(lines)


def _render_digest_prompt(payload: dict) -> str:
    """Render weekly digest prompt from mistral_inputs.yaml (with safe fallback)."""
    inputs = _load_mistral_inputs()
    digest_cfg = inputs.get("digest", {})
    template = digest_cfg.get(
        "weekly_summary_template",
        _DEFAULT_MISTRAL_INPUTS["digest"]["weekly_summary_template"],
    )
    compact_payload = _compact_digest_for_prompt(payload)
    digest_json = json.dumps(compact_payload, ensure_ascii=False, indent=2)
    prompt_brief = _digest_brief_for_prompt(payload)
    profile = _user_profile_for_prompt()
    addressing = _user_addressing_instruction()
    if profile and "{user_profile}" not in template:
        template = (
            f"{template}\n\n"
            "Contexte utilisateur (a prendre en compte dans le digest):\n"
            "{user_profile}"
        )
    if addressing and "{user_addressing}" not in template:
        template = f"{template}\n\n" "Consigne d'adresse:\n" "{user_addressing}"
    try:
        return template.format(
            days=payload.get("days"),
            digest_json=digest_json,
            compact_brief=prompt_brief,
            weeks_ago=payload.get("weeks_ago"),
            window_start=payload.get("window_start"),
            window_end=payload.get("window_end"),
            user_profile=profile,
            user_addressing=addressing,
        )
    except Exception as e:
        log.warning(f"Invalid digest prompt template; using default. Error: {e}")
        fallback = _DEFAULT_MISTRAL_INPUTS["digest"]["weekly_summary_template"]
        if profile and "{user_profile}" not in fallback:
            fallback = f"{fallback}\n\n" "Contexte utilisateur:\n" "{user_profile}"
        if addressing and "{user_addressing}" not in fallback:
            fallback = f"{fallback}\n\n" "Consigne d'adresse:\n" "{user_addressing}"
        return fallback.format(
            days=payload.get("days"),
            digest_json=digest_json,
            user_profile=profile,
            user_addressing=addressing,
        )


@app.post("/digest/weekly/summary")
async def weekly_digest_summary(request: Request, x_api_key: str = Header(None)):
    """Start background generation for a 4-5 sentence weekly digest summary."""
    _verify_api_key(x_api_key)
    body = await request.json()
    days = int(body.get("days", 7)) if isinstance(body, dict) else 7
    days = max(1, min(days, 31))
    weeks_ago = int(body.get("weeks_ago", 0)) if isinstance(body, dict) else 0
    weeks_ago = max(0, min(weeks_ago, 26))
    force_raw = body.get("force", False) if isinstance(body, dict) else False
    force = (
        str(force_raw).strip().lower() in {"1", "true", "yes", "on"}
        if not isinstance(force_raw, bool)
        else force_raw
    )

    cfg = _load_config()
    digest_cfg = cfg.get("digest", {})
    try:
        max_pending_seconds = float(digest_cfg.get("max_pending_seconds", 150))
    except Exception:
        max_pending_seconds = 150.0
    today = datetime.now().date()
    current_monday = today - timedelta(days=today.weekday())
    week_start_date = current_monday - timedelta(days=weeks_ago * 7)
    week_end_date = week_start_date + timedelta(days=6)
    if week_end_date >= today:
        return JSONResponse(
            {
                "status": "not-ready",
                "message": "La semaine n'est pas terminee. Reviens plus tard.",
                "window_start": week_start_date.strftime("%Y-%m-%d"),
                "window_end": week_end_date.strftime("%Y-%m-%d"),
            },
            status_code=409,
        )

    job_key = f"weekly:{days}:w{weeks_ago}"
    summary_file = _digest_summary_path(days, weeks_ago)

    if force:
        with _digest_lock:
            _digest_job_tokens[job_key] = int(_digest_job_tokens.get(job_key, 0)) + 1
            _digest_summary_results.pop(job_key, None)
            _digest_summary_errors.pop(job_key, None)
            _digest_summary_queue.pop(job_key, None)
        if summary_file.exists():
            try:
                summary_file.unlink()
            except Exception:
                pass

    if not force:
        persisted = _load_persisted_digest_summary(days, weeks_ago)
        if persisted:
            with _digest_lock:
                _digest_summary_results[job_key] = persisted
            return JSONResponse({"status": "ok", **persisted})

    with _digest_lock:
        token = int(_digest_job_tokens.get(job_key, 0))
        if job_key in _digest_summary_results:
            current_profile_sig = _user_profile_signature()
            cached_profile_sig = (_digest_summary_results.get(job_key) or {}).get(
                "profile_signature"
            )
            if cached_profile_sig != current_profile_sig:
                _digest_summary_results.pop(job_key, None)
            else:
                return JSONResponse(
                    {"status": "ok", **_digest_summary_results[job_key]}
                )

        if job_key in _digest_summary_queue:
            started_at = float(_digest_summary_queue.get(job_key) or 0)
            if (
                max_pending_seconds > 0
                and started_at > 0
                and (time.time() - started_at) > max_pending_seconds
            ):
                _digest_summary_queue.pop(job_key, None)
                _digest_summary_errors[job_key] = (
                    "Digest summary job timed out (stale pending job cleared)."
                )
            else:
                return JSONResponse({"status": "pending", "job_key": job_key})

        if job_key in _digest_summary_errors:
            # If we reached here after stale cleanup, continue and start a fresh job.
            _digest_summary_errors.pop(job_key, None)

        if job_key in _digest_summary_queue:
            return JSONResponse({"status": "pending", "job_key": job_key})

        _digest_summary_queue[job_key] = time.time()
        _digest_summary_errors.pop(job_key, None)

    worker_token = token

    def run_summary_job():
        job_started_at = time.perf_counter()

        def elapsed_seconds() -> float:
            return round(max(0.0, time.perf_counter() - job_started_at), 2)

        try:
            payload = _compute_weekly_digest_payload(days, weeks_ago)
            if int(payload.get("total_entries") or 0) == 0:
                if not _is_digest_job_current(job_key, worker_token):
                    return
                with _digest_lock:
                    if not _is_digest_job_current(job_key, worker_token):
                        return
                    _digest_summary_results[job_key] = {
                        "source": "fallback",
                        "summary": _fallback_digest_summary(payload),
                        "digest": payload,
                        "generation_seconds": elapsed_seconds(),
                        "profile_signature": _user_profile_signature(),
                    }
                    _persist_digest_summary(
                        days, weeks_ago, _digest_summary_results[job_key]
                    )
                return

            cfg = _load_config()
            digest_cfg = cfg.get("digest", {})
            if _digest_guard_is_cooling_down():
                if not _is_digest_job_current(job_key, worker_token):
                    return
                with _digest_lock:
                    if not _is_digest_job_current(job_key, worker_token):
                        return
                    _digest_summary_results[job_key] = {
                        "source": "fallback",
                        "summary": _fallback_digest_summary(payload),
                        "digest": payload,
                        "generation_seconds": elapsed_seconds(),
                        "profile_signature": _user_profile_signature(),
                    }
                    _persist_digest_summary(
                        days, weeks_ago, _digest_summary_results[job_key]
                    )
                return

            prompt = _render_digest_prompt(payload)

            ollama_cfg = cfg.get("ollama", {})
            host = ollama_cfg.get("host", "http://127.0.0.1:11434")
            model = ollama_cfg.get("model", "mistral")

            try:
                import requests as req

                attempts = [
                    {
                        "num_predict": int(digest_cfg.get("num_predict", 80)),
                        "temperature": float(digest_cfg.get("temperature", 0.3)),
                        "timeout": _normalize_timeout_seconds(
                            digest_cfg.get("request_timeout_seconds", 45), 45
                        ),
                    },
                    {
                        "num_predict": int(digest_cfg.get("retry_num_predict", 56)),
                        "temperature": float(digest_cfg.get("retry_temperature", 0.25)),
                        "timeout": _normalize_timeout_seconds(
                            digest_cfg.get("retry_timeout_seconds", 35), 35
                        ),
                    },
                ]

                for idx, attempt in enumerate(attempts, start=1):
                    try:
                        r = req.post(
                            f"{host}/api/chat",
                            json={
                                "model": model,
                                "stream": False,
                                "keep_alive": "15m",
                                "messages": [{"role": "user", "content": prompt}],
                                "options": {
                                    "temperature": attempt["temperature"],
                                    "num_predict": attempt["num_predict"],
                                },
                            },
                            timeout=attempt["timeout"],
                        )
                        if r.status_code == 200:
                            body = r.json()
                            summary = str(
                                (body.get("message") or {}).get("content") or ""
                            ).strip()
                            if summary:
                                _digest_guard_record_success()
                                if not _is_digest_job_current(job_key, worker_token):
                                    return
                                with _digest_lock:
                                    if not _is_digest_job_current(
                                        job_key, worker_token
                                    ):
                                        return
                                    _digest_summary_results[job_key] = {
                                        "source": "mistral",
                                        "summary": summary,
                                        "digest": payload,
                                        "generation_seconds": elapsed_seconds(),
                                        "profile_signature": _user_profile_signature(),
                                    }
                                    _persist_digest_summary(
                                        days,
                                        weeks_ago,
                                        _digest_summary_results[job_key],
                                    )
                                return

                        # Compatibility fallback for older Ollama behaviors.
                        r2 = req.post(
                            f"{host}/api/generate",
                            json={
                                "model": model,
                                "prompt": prompt,
                                "stream": False,
                                "keep_alive": "15m",
                                "options": {
                                    "temperature": attempt["temperature"],
                                    "num_predict": attempt["num_predict"],
                                },
                            },
                            timeout=attempt["timeout"],
                        )
                        if r2.status_code == 200:
                            summary2 = str((r2.json().get("response") or "")).strip()
                            if summary2:
                                _digest_guard_record_success()
                                if not _is_digest_job_current(job_key, worker_token):
                                    return
                                with _digest_lock:
                                    if not _is_digest_job_current(
                                        job_key, worker_token
                                    ):
                                        return
                                    _digest_summary_results[job_key] = {
                                        "source": "mistral",
                                        "summary": summary2,
                                        "digest": payload,
                                        "generation_seconds": elapsed_seconds(),
                                        "profile_signature": _user_profile_signature(),
                                    }
                                    _persist_digest_summary(
                                        days,
                                        weeks_ago,
                                        _digest_summary_results[job_key],
                                    )
                                return

                        _digest_guard_record_failure(digest_cfg)
                    except Exception as e:
                        _digest_guard_record_failure(digest_cfg)
                        log.warning(f"Weekly digest summary attempt {idx} failed: {e}")
            except Exception as e:
                log.warning(f"Weekly digest summary fallback: {e}")

            with _digest_lock:
                if not _is_digest_job_current(job_key, worker_token):
                    return
                _digest_summary_results[job_key] = {
                    "source": "fallback",
                    "summary": _fallback_digest_summary(payload),
                    "digest": payload,
                    "generation_seconds": elapsed_seconds(),
                    "profile_signature": _user_profile_signature(),
                }
                _persist_digest_summary(
                    days, weeks_ago, _digest_summary_results[job_key]
                )
        except Exception as e:
            with _digest_lock:
                if _is_digest_job_current(job_key, worker_token):
                    _digest_summary_errors[job_key] = str(e)
            log.error(f"Weekly digest summary failed: {e}")
        finally:
            with _digest_lock:
                if _is_digest_job_current(job_key, worker_token):
                    _digest_summary_queue.pop(job_key, None)

    threading.Thread(target=run_summary_job, daemon=True).start()
    return JSONResponse({"status": "pending", "job_key": job_key})


@app.get("/digest/weekly/summary-status")
def weekly_digest_summary_status(
    days: int = 7, weeks_ago: int = 0, x_api_key: str = Header(None)
):
    """Get status for background weekly digest summary generation."""
    _verify_api_key(x_api_key)
    days = max(1, min(int(days or 7), 31))
    weeks_ago = max(0, min(int(weeks_ago or 0), 26))
    job_key = f"weekly:{days}:w{weeks_ago}"
    cfg = _load_config()
    digest_cfg = cfg.get("digest", {})
    try:
        max_pending_seconds = float(digest_cfg.get("max_pending_seconds", 150))
    except Exception:
        max_pending_seconds = 150.0
    stale_job = False

    with _digest_lock:
        if job_key in _digest_summary_results:
            current_profile_sig = _user_profile_signature()
            cached_profile_sig = (_digest_summary_results.get(job_key) or {}).get(
                "profile_signature"
            )
            if cached_profile_sig != current_profile_sig:
                _digest_summary_results.pop(job_key, None)
            else:
                return JSONResponse(
                    {"status": "ok", **_digest_summary_results[job_key]}
                )
        if job_key in _digest_summary_queue:
            started_at = float(_digest_summary_queue.get(job_key) or 0)
            if (
                max_pending_seconds > 0
                and started_at > 0
                and (time.time() - started_at) > max_pending_seconds
            ):
                _digest_summary_queue.pop(job_key, None)
                _digest_summary_errors[job_key] = "Digest summary job timed out."
                stale_job = True
            else:
                return JSONResponse(
                    {
                        "status": "pending",
                        "pending_seconds": (
                            round(max(0.0, time.time() - started_at), 1)
                            if started_at > 0
                            else None
                        ),
                    }
                )
        if job_key in _digest_summary_errors:
            return JSONResponse(
                {"status": "error", "error": _digest_summary_errors[job_key]}
            )

    if stale_job:
        result = _build_persisted_fallback_result(days, weeks_ago, "LLM timeout")
        with _digest_lock:
            _digest_summary_results[job_key] = result
            _digest_summary_errors.pop(job_key, None)
        return JSONResponse({"status": "ok", **result})

    persisted = _load_persisted_digest_summary(days, weeks_ago)
    if persisted:
        with _digest_lock:
            _digest_summary_results[job_key] = persisted
        return JSONResponse({"status": "ok", **persisted})
    return JSONResponse({"status": "idle"})


@app.post("/digest/weekly/summary/cancel")
async def cancel_weekly_digest_summary(request: Request, x_api_key: str = Header(None)):
    """Cancel an in-flight weekly digest summary generation job."""
    _verify_api_key(x_api_key)
    body = await request.json()
    days = int(body.get("days", 7)) if isinstance(body, dict) else 7
    days = max(1, min(days, 31))
    weeks_ago = int(body.get("weeks_ago", 0)) if isinstance(body, dict) else 0
    weeks_ago = max(0, min(weeks_ago, 26))

    job_key = f"weekly:{days}:w{weeks_ago}"
    with _digest_lock:
        _digest_job_tokens[job_key] = int(_digest_job_tokens.get(job_key, 0)) + 1
        was_pending = job_key in _digest_summary_queue
        _digest_summary_queue.pop(job_key, None)
        _digest_summary_errors.pop(job_key, None)

    return JSONResponse(
        {
            "status": "ok",
            "job_key": job_key,
            "canceled": bool(was_pending),
        }
    )


@app.get("/search")
def search_entries(q: str, x_api_key: str = Header(None)):
    """Full text search across all transcripts. Query param: q"""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    results = []

    if not q or len(q.strip()) < 2:
        return JSONResponse([])

    query = q.strip().lower()

    if entries_dir.exists():
        for entry in sorted(entries_dir.iterdir(), reverse=True):
            if not entry.is_dir():
                continue
            meta_file = entry / "meta.json"
            if not meta_file.exists():
                continue

            # Search across all transcript versions
            transcript = ""
            for fname in [
                "transcript_user.txt",
                "transcript_corrected.txt",
                "transcript_raw.txt",
            ]:
                f = entry / fname
                if f.exists():
                    transcript = f.read_text()
                    break

            if query in transcript.lower():
                with open(meta_file) as f:
                    meta = json.load(f)

                _apply_dream_date_fallback(meta)

                # Find the matching excerpt
                idx = transcript.lower().find(query)
                start = max(0, idx - 60)
                end = min(len(transcript), idx + len(query) + 60)
                excerpt = (
                    ("…" if start > 0 else "")
                    + transcript[start:end]
                    + ("…" if end < len(transcript) else "")
                )

                meta["search_excerpt"] = excerpt
                meta["search_match_pos"] = idx
                results.append(meta)

    return JSONResponse(results)


@app.get("/vocabulary")
def get_vocabulary(x_api_key: str = Header(None)):
    """Get the current vocabulary list."""
    _verify_api_key(x_api_key)
    config = _load_config()
    vocab_file = Path(config.get("vocabulary_file", ""))
    if not vocab_file.exists():
        return JSONResponse({"vocabulary": ""})
    return JSONResponse({"vocabulary": vocab_file.read_text()})


@app.post("/vocabulary/update")
async def update_vocabulary(request: Request, x_api_key: str = Header(None)):
    """Replace the entire vocabulary list. Body: {\"vocabulary\": \"word1, word2, ...\"}"""
    _verify_api_key(x_api_key)
    config = _load_config()
    vocab_file = Path(config.get("vocabulary_file", ""))
    vocab_file.parent.mkdir(parents=True, exist_ok=True)

    body = await request.json()
    vocabulary = body.get("vocabulary", "")
    vocab_file.write_text(vocabulary)

    log.info(f"Vocabulary updated: {vocabulary[:50]}...")
    return JSONResponse({"status": "ok"})


@app.post("/vocabulary/add")
async def add_vocabulary_word(request: Request, x_api_key: str = Header(None)):
    """Add a single word to vocabulary. Body: {\"word\": \"...\"}"""
    _verify_api_key(x_api_key)
    config = _load_config()
    vocab_file = Path(config.get("vocabulary_file", ""))
    vocab_file.parent.mkdir(parents=True, exist_ok=True)

    body = await request.json()
    word = body.get("word", "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required")

    existing = vocab_file.read_text().strip() if vocab_file.exists() else ""
    words = [w.strip() for w in existing.split(",") if w.strip()]

    if word not in words:
        words.append(word)
        vocab_file.write_text(", ".join(words))
        log.info(f"Vocabulary word added: {word}")
        return JSONResponse({"status": "ok", "added": True})
    else:
        return JSONResponse(
            {"status": "ok", "added": False, "message": "Already in vocabulary"}
        )


@app.get("/profile")
def get_profile(x_api_key: str = Header(None)):
    """Get editable user profile used as LLM context."""
    _verify_api_key(x_api_key)
    return JSONResponse(_load_user_profile())


@app.post("/profile/update")
async def update_profile(request: Request, x_api_key: str = Header(None)):
    """Replace user profile used by digest/interpretation generation."""
    _verify_api_key(x_api_key)
    body = await request.json()
    profile = _sanitize_user_profile(body if isinstance(body, dict) else {})
    _save_user_profile(profile)
    return JSONResponse({"status": "ok", "profile": profile})


@app.post("/push/subscribe")
async def push_subscribe(request: Request, x_api_key: str = Header(None)):
    """Register a PWA push subscription."""
    _verify_api_key(x_api_key)
    body = await request.json()
    add_subscription(body)
    return JSONResponse({"status": "ok"})


@app.delete("/push/subscribe")
async def push_unsubscribe(request: Request, x_api_key: str = Header(None)):
    """Unregister a push subscription. Body: {\"endpoint\": \"...\"}"""
    _verify_api_key(x_api_key)
    body = await request.json()
    endpoint = body.get("endpoint")
    if endpoint:
        remove_subscription(endpoint)
    return JSONResponse({"status": "ok"})


@app.get("/push/key")
def push_public_key(x_api_key: str = Header(None)):
    """Return the VAPID public key for the PWA."""
    _verify_api_key(x_api_key)
    config = _load_config()
    public_key = config.get("push", {}).get("vapid_public_key", "")
    return JSONResponse({"public_key": public_key})


# ── Serve PWA static files ─────────────────────────────────────────────────────
pwa_dist = Path.home() / "dreamserver" / "pwa" / "dist"
if pwa_dist.exists():
    cfg = _load_config()
    pwa_cfg = cfg.get("pwa", {}) if isinstance(cfg, dict) else {}
    pwa_base = str(pwa_cfg.get("base_path", "/app")).strip() or "/app"
    if not pwa_base.startswith("/"):
        pwa_base = f"/{pwa_base}"
    if len(pwa_base) > 1:
        pwa_base = pwa_base.rstrip("/")
    app.mount(pwa_base, StaticFiles(directory=str(pwa_dist), html=True), name="pwa")
