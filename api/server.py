"""
server.py - FastAPI server for Sandman
Receives audio uploads from DreamCatcher
Automatically transcribes after upload
Optionally corrects after transcription
Sends push notifications when transcript is ready
Serves PWA static files over HTTPS
"""

import json
import logging
import re
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline.transcriber import Transcriber
from pipeline.corrector import Corrector
from notifications.push import send_transcript_ready

logging.basicConfig(level=logging.INFO, format="%(asctime)s [dreamserver] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
app.include_router(settings_router)

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

from api.interpretation import (
    build_interpreter_prompt, interpreter_prompt_signature,
    compact_interpret_prompt, anti_paraphrase_prompt,
    local_interpretation_fallback, run_interpretation_job,
    word_overlap_ratio,
)
from api.digest import fallback_digest_summary as _fallback_digest_summary
from api.digest import render_digest_prompt as _render_digest_prompt
from api.config import (
    DEFAULT_MISTRAL_INPUTS as _DEFAULT_MISTRAL_INPUTS,
    DIGEST_SUMMARIES_DIR, SEMANTIC_GROUPS_FILE,
    load_config as _load_config, load_mistral_inputs as _load_mistral_inputs,
)
from api.profile import (
    load_user_profile as _load_user_profile,
    user_addressing_instruction as _user_addressing_instruction,
    user_profile_for_prompt as _user_profile_for_prompt,
    user_profile_signature as _user_profile_signature,
)
from api.storage import (
    entry_path as _entry_path, find_audio as _find_audio,
    iter_entry_paths as _iter_entry_paths, read_meta as _read_meta,
    read_preferred_transcript as _read_preferred_transcript,
    read_transcripts as _read_transcripts, update_meta as _update_meta,
    write_meta as _write_meta, write_transcript as _write_transcript,
)
from api.analytics import (
    compute_stats as _compute_stats,
    compute_weekly_digest as _compute_weekly_digest,
    search_entries as _search_entries,
)
from api.semantic_store import SemanticStore
from api.interpretation_store import InterpretationStore
from api.interpretation_service import InterpretationService
from api.routes.settings import router as settings_router
from api.dream_map_rules import (
    collect_tags as _dream_map_collect_tags,
    is_content_word as _dream_map_is_content_word,
    is_keyword as _dream_map_is_keyword,
    normalize_tag as _normalize_tag,
)

_semantic_store = SemanticStore(SEMANTIC_GROUPS_FILE, log)






def _digest_summary_path(days: int, weeks_ago: int) -> Path:
    DIGEST_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    return DIGEST_SUMMARIES_DIR / f"weekly_{days}_w{weeks_ago}.json"


def _interpretation_meta_path(entry_dir: Path, interpreter_key: str) -> Path:
    return entry_dir / f"interpretation_{interpreter_key}.json"


def _read_interpretation_meta(entry_dir: Path, interpreter_key: str) -> dict:
    path = _interpretation_meta_path(entry_dir, interpreter_key)
    if not path.exists():
        return {}
    try:
        with open(path) as meta_file:
            data = json.load(meta_file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_interpretation_source(entry_dir: Path, interpreter_key: str) -> str:
    return _read_interpretation_meta(entry_dir, interpreter_key).get("source") or "mistral"


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
    with open(meta_path, "w") as meta_file:
        json.dump(payload, meta_file, ensure_ascii=False, indent=2)


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
        _fallback_retry_queue.append({
            **job,
            "next_try_at": float(job.get("next_try_at") or 0),
            "tries": int(job.get("tries") or 0),
        })
        _fallback_retry_pending.add(key)


def _load_persisted_digest_summary(days: int, weeks_ago: int):
    path = _digest_summary_path(days, weeks_ago)
    if not path.exists():
        return None
    try:
        with open(path) as summary_file:
            data = json.load(summary_file)
        if not isinstance(data, dict) or not data.get("summary"):
            return None
        if data.get("profile_signature") != _user_profile_signature():
            return None
        return data
    except Exception:
        return None


def _persist_digest_summary(days: int, weeks_ago: int, payload: dict):
    path = _digest_summary_path(days, weeks_ago)
    stored = {
        "source": payload.get("source"),
        "summary": payload.get("summary"),
        "digest": payload.get("digest"),
        "created_at": datetime.now().isoformat(),
        "generation_seconds": payload.get("generation_seconds"),
        "profile_signature": payload.get("profile_signature") or _user_profile_signature(),
    }
    with open(path, "w") as summary_file:
        json.dump(stored, summary_file, ensure_ascii=False, indent=2)


def _build_persisted_fallback_result(days: int, weeks_ago: int, reason: str = "") -> dict:
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


















def _ensure_semantic_store_loaded():
    _semantic_store.ensure_loaded()


def _reset_semantic_store():
    _semantic_store.reset()


def _current_semantic_generation() -> int:
    return _semantic_store.current_generation()


def _save_semantic_store():
    _semantic_store.save()


def _classify_tag_with_mistral(tag: str):
    _ensure_semantic_store_loaded()
    cfg = _load_config()
    ollama_cfg = cfg.get("ollama", {})
    host = ollama_cfg.get("host", "http://127.0.0.1:11434")
    model = ollama_cfg.get("model", "mistral")
    groups = _semantic_store.groups()

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
            _semantic_store.assign(tag, group, generation)
            _save_semantic_store()
            log.info(f"Semantic group assigned: {tag} -> {group}")
        else:
            log.warning(f"No semantic group assigned yet for tag: {tag}")
    finally:
        _semantic_store.finish_tag(tag)


def _enqueue_tag_semantic_classification(tag: str, generation: int | None = None):
    t = _normalize_tag(tag)
    if not t:
        return
    _ensure_semantic_store_loaded()
    current_generation = _semantic_store.begin_tag(t, generation)
    if current_generation is None:
        return
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
    entry_dir = _entry_path(entries_dir, timestamp)
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
    _write_meta(entry_dir, meta)

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
    entry_dir = _entry_path(entries_dir, timestamp)
    entry_dir.mkdir(parents=True, exist_ok=True)

    _write_transcript(entry_dir, "raw", text)
    _write_transcript(entry_dir, "corrected", text)

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
    _write_meta(entry_dir, meta)

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
        for entry in _iter_entry_paths(entries_dir):
            meta = _read_meta(entry)
            if meta is not None:
                _apply_dream_date_fallback(meta)

                # Surface interpretation background activity at entry level.
                ts = meta.get("timestamp", entry.name)
                prefix = f"{ts}_"
                meta["interpretation_pending"] = any(
                    job_key.startswith(prefix)
                    for job_key in _interpretation_queue.keys()
                )

                # Add transcript preview — prefer user > corrected > raw
                preview = _read_preferred_transcript(entry)
                if preview:
                    meta["transcript_preview"] = preview[:150]
                entries.append(meta)
    return JSONResponse(entries)


@app.get("/entries/{timestamp}")
def get_entry(timestamp: str, x_api_key: str = Header(None)):
    """Get a single entry with all its transcripts."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = _entry_path(entries_dir, timestamp)

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    meta = _read_meta(entry_dir) or {}

    _apply_dream_date_fallback(meta)

    meta.update(_read_transcripts(entry_dir))

    return JSONResponse(meta)


@app.get("/entries/{timestamp}/audio")
def get_audio(timestamp: str, x_api_key: str = Header(None)):
    """Stream the audio file for an entry."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = _entry_path(entries_dir, timestamp)

    audio = _find_audio(entry_dir)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(str(audio))


@app.post("/entries/{timestamp}/correct")
def correct_entry(timestamp: str, x_api_key: str = Header(None)):
    """Manually trigger LLM correction for a specific entry."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = _entry_path(entries_dir, timestamp)

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    if _read_meta(entry_dir) is not None:
        _update_meta(entry_dir, {"corrected": False})

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
    entry_dir = _entry_path(entries_dir, timestamp)

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    tags = body.get("tags", [])

    meta = _read_meta(entry_dir) or {}
    meta["tags"] = tags
    _write_meta(entry_dir, meta)

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
    entry_dir = _entry_path(entries_dir, timestamp)

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    _write_transcript(entry_dir, "user", text)
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
    entry_dir = _entry_path(entries_dir, timestamp)

    if not entry_dir.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    body = await request.json()
    dream_date = _normalize_dream_date(body.get("dream_date"))
    if dream_date is None:
        raise HTTPException(status_code=400, detail="dream_date is required")

    meta = _read_meta(entry_dir) or {}

    meta["dream_date"] = dream_date

    _write_meta(entry_dir, meta)

    log.info(f"Dream date updated for {timestamp}: {dream_date}")
    return JSONResponse({"status": "ok", "dream_date": dream_date})


@app.delete("/entries/{timestamp}")
def delete_entry(timestamp: str, x_api_key: str = Header(None)):
    """Delete an entry and all its files."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    entry_dir = _entry_path(entries_dir, timestamp)

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
_interpretation_store = InterpretationStore()
_interpretation_queue = _interpretation_store.queue
_interpretation_errors = _interpretation_store.errors
_interpretation_job_tokens = _interpretation_store.tokens
_interpretation_service = InterpretationService(
    store=_interpretation_store,
    run_job_fn=run_interpretation_job,
    load_config_fn=_load_config,
    write_interpretation_fn=_write_interpretation,
    normalize_timeout_fn=_normalize_timeout_seconds,
    logger=log,
)


def _cleanup_stale_interpretations():
    _interpretation_service.cleanup_stale()


def _is_digest_job_current(job_key: str, token: int) -> bool:
    return int(_digest_job_tokens.get(job_key, 0)) == int(token)


def _is_interpretation_job_current(job_key: str, token: int) -> bool:
    return _interpretation_service.is_current(job_key, token)


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

    _interpretation_service.start(
        entry_dir=entry_dir,
        timestamp=timestamp,
        interpreter_key=interpreter_key,
        text=text,
        job_key=job_key,
        prompt_signature=current_prompt_signature,
    )
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

    cache_snapshot, pending_snapshot = _semantic_store.snapshot()

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

    cache, pending = _semantic_store.snapshot()

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
    """Return statistics computed from all transcribed entries."""
    _verify_api_key(x_api_key)
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    return JSONResponse(_compute_stats(entries_dir))


@app.get("/digest/weekly")
def weekly_digest(days: int = 7, weeks_ago: int = 0, x_api_key: str = Header(None)):
    """Return a compact weekly digest of recent dreams for the PWA."""
    _verify_api_key(x_api_key)
    return JSONResponse(_compute_weekly_digest_payload(days, weeks_ago))


def _compute_weekly_digest_payload(days: int = 7, weeks_ago: int = 0):
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    return _compute_weekly_digest(entries_dir, days, weeks_ago)




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

            prompt = _render_digest_prompt(
                payload,
                _load_mistral_inputs(),
                _DEFAULT_MISTRAL_INPUTS,
                profile=_user_profile_for_prompt(),
                addressing=_user_addressing_instruction(),
                logger=log,
            )

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
    return JSONResponse(
        _search_entries(entries_dir, q, normalize_meta=_apply_dream_date_fallback)
    )


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
