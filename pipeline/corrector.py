"""
corrector.py — LLM correction pipeline for Sandman
- Corrects Whisper transcription errors using Ollama/Mistral
- Optional — controlled by config and per-request flag
- Conservative corrections only (homophones, numbers, accents)
- Saves corrected transcript alongside raw transcript
- Updates meta.json with correction status
"""

import json
import logging
import threading
import queue
from datetime import datetime
from pathlib import Path

import requests
import yaml

# ── Logging ────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / "dreamserver" / "config.yaml"

CORRECTION_PROMPT = """Tu es un assistant de correction pour un journal de rêves personnel en français.
Le texte a été transcrit automatiquement depuis une reconnaissance vocale.
Corrige uniquement les erreurs probables de transcription:
- homophones mal choisis selon le contexte (conte/compte, vers/verre, est/et, a/à, ou/où, etc.)
- accents manquants ou incorrects
- conjugaisons mal retranscrites
- mots composés mal formés (chef-d'œuvre, court-métrage, etc.)
- nombres écrits en chiffres alors qu'ils devraient être en lettres
Ne modifie pas le vocabulaire, le style ou le sens original.
NE PAS ajouter d'explications, de liste de corrections, de commentaires ou de guillemets.
Retourner UNIQUEMENT le texte corrigé, rien d'autre.

Texte: \"{text}\""""


def _load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


class Corrector:
    """
    Background LLM correction worker for Sandman.

    Processes a queue of entry folders, correcting transcript_raw.txt
    and saving the result as transcript_corrected.txt.

    Optional — only runs if correction is enabled in config or per-request.

    Usage:
        c = Corrector(on_complete=my_callback)
        c.start()
        c.enqueue(entry_path)
        c.resume_pending()  # call once at startup if correction is enabled
    """

    def __init__(self, on_complete=None):
        self.on_complete = on_complete
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._active = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        self._thread.start()
        log.info("Corrector started")

    def enqueue(self, entry_path: Path):
        self._queue.put(entry_path)
        log.info(f"Queued for correction: {entry_path.name}")

    def resume_pending(self):
        """Scan entries/ for transcribed but uncorrected entries and re-queue."""
        config = _load_config()
        entries_dir = Path(config["storage"]["entries_dir"])
        if not entries_dir.exists():
            return
        for entry in sorted(entries_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta = _read_meta(entry)
            if (
                meta
                and meta.get("transcribed")
                and not meta.get("corrected")
                and (entry / "transcript_raw.txt").exists()
            ):
                log.info(f"Resuming pending correction: {entry.name}")
                self.enqueue(entry)

    @property
    def is_active(self):
        return self._active

    # ── Internal ───────────────────────────────────────────────────────────────

    def _worker(self):
        while True:
            entry_path = self._queue.get()
            try:
                self._active = True
                self._correct_entry(entry_path)
            except Exception as e:
                import traceback

                log.error(f"Correction failed for {entry_path.name}: {e}")
                log.error(traceback.format_exc())
                _update_meta(
                    entry_path,
                    {
                        "correction_error": str(e),
                        "correction_error_time": datetime.now().isoformat(),
                    },
                )
            finally:
                self._active = False
                self._queue.task_done()

    def _correct_entry(self, entry_path: Path):
        raw_file = entry_path / "transcript_raw.txt"
        if not raw_file.exists():
            log.warning(f"No transcript_raw.txt in {entry_path.name}, skipping")
            return

        meta = _read_meta(entry_path) or {}
        if meta.get("corrected"):
            log.info(f"{entry_path.name} already corrected, skipping")
            return

        raw_text = raw_file.read_text().strip()
        if not raw_text:
            log.warning(f"Empty transcript in {entry_path.name}, skipping")
            return

        log.info(f"Correcting: {entry_path.name}")

        corrected_text = self._call_ollama(raw_text)

        if corrected_text:
            corrected_file = entry_path / "transcript_corrected.txt"
            corrected_file.write_text(corrected_text)

            _update_meta(
                entry_path,
                {"corrected": True, "corrected_at": datetime.now().isoformat()},
            )

            log.info(f"Correction done: {entry_path.name}")

            if self.on_complete:
                self.on_complete(entry_path, corrected_text)
        else:
            log.warning(f"Correction returned empty result for {entry_path.name}")
            corrected_file = entry_path / "transcript_corrected.txt"
            corrected_file.write_text(raw_text)
            _update_meta(
                entry_path,
                {
                    "corrected": True,
                    "corrected_at": datetime.now().isoformat(),
                    "correction_fallback": True,
                },
            )

    def _call_ollama(self, text: str) -> str:
        config = _load_config()
        ollama_cfg = config.get("ollama", {})
        model = ollama_cfg.get("model", "mistral")
        host = ollama_cfg.get("host", "http://localhost:11434")
        url = f"{host}/api/generate"

        prompt = CORRECTION_PROMPT.format(text=text)

        response = requests.post(
            url, json={"model": model, "prompt": prompt, "stream": False}, timeout=600
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama returned {response.status_code}: {response.text}"
            )

        result = response.json().get("response", "").strip()
        result = _clean_ollama_output(result)
        return result


# ── Output cleaning ────────────────────────────────────────────────────────────


def _clean_ollama_output(text: str) -> str:
    """Remove common Mistral artifacts: surrounding quotes and explanation sections."""
    text = text.strip()

    # Strip surrounding quotes
    if text.startswith('"') and '"' in text[1:]:
        first_quote_end = text.index('"', 1)
        text = text[1:first_quote_end]

    # Remove explanation lines Mistral sometimes adds
    explanation_markers = [
        "correction",
        "modification",
        "changement",
        "note:",
        "remarque",
        "explication",
        "voici",
    ]
    lines = text.split("\n")
    text_lines = []
    for line in lines:
        if any(marker in line.lower() for marker in explanation_markers):
            break
        text_lines.append(line)

    result = " ".join(s.strip() for s in text_lines if s.strip())
    return result.strip()


# ── meta.json helpers ──────────────────────────────────────────────────────────


def _read_meta(entry_path: Path):
    meta_file = entry_path / "meta.json"
    if not meta_file.exists():
        return None
    with open(meta_file) as f:
        return json.load(f)


def _update_meta(entry_path: Path, updates: dict):
    meta_file = entry_path / "meta.json"
    meta = _read_meta(entry_path) or {}
    meta.update(updates)
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Test: correct all transcribed entries fresh.
    Usage: python3 corrector.py
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [corrector] %(message)s"
    )

    def on_complete(path, text):
        print(f"\n✓ Corrected transcript:\n{text}\n")

    # Reset corrected flag on all entries for fresh test
    config = _load_config()
    entries_dir = Path(config["storage"]["entries_dir"])
    for entry in sorted(entries_dir.iterdir()):
        if entry.is_dir():
            meta_file = entry / "meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    meta = json.load(f)
                if meta.get("corrected"):
                    meta["corrected"] = False
                    corrected = entry / "transcript_corrected.txt"
                    if corrected.exists():
                        corrected.unlink()
                    with open(meta_file, "w") as f:
                        json.dump(meta, f, indent=2)

    c = Corrector(on_complete=on_complete)
    c.start()
    c.resume_pending()

    c._queue.join()
    print("Done.")
